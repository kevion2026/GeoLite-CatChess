/* CatChess-V1.0-pro 正式版 本地对弈服务
 *
 * 作用：把 UCI 引擎包成浏览器可用的 HTTP 接口。
 *   GET  /               前端页面
 *   GET  /api/stream     SSE：引擎思考过程（depth/score/nodes/nps）与状态
 *   GET  /api/status     引擎是否就绪
 *   GET  /api/models     列出可切换的 CatChess 模型（exe）
 *   POST /api/model      {name:"CatChess-...exe"} 切换引擎/模型并重启
 *   POST /api/think      {moves:[...], ms:600}  → {bestmove, info:[...]}
 *   POST /api/eval       {moves:[...]}           → {cp}   （融合后的静态评估）
 *   POST /api/perft      {moves:[...], depth:3}  → {nodes}（用于前端规则自检）
 *   POST /api/newgame    {}                      → 清空置换表
 *
 * 注意：引擎是单线程阻塞搜索，搜索期间读不到 stdin。所有命令因此串行排队，
 * 不会出现「go 还没回 bestmove 就发下一条」导致协议错位。
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const ROOT = __dirname;
const PROJECT_ROOT = path.resolve(ROOT, "..");
/* 模型权重编译在 exe 内，切换“模型”=切换可执行文件。EXE 允许运行时改。 */
let EXE =
  process.env.CATCHESS_EXE ||
  path.join(PROJECT_ROOT, "CatChess-V1.0-pro.exe");
const PORT = Number(process.env.PORT || 8770);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

// ---------------------------------------------------------------- 事件广播
const clients = new Set();
function broadcast(obj) {
  const s = "data: " + JSON.stringify(obj) + "\n\n";
  for (const c of clients) {
    try {
      c.write(s);
    } catch (e) {
      clients.delete(c);
    }
  }
}

// ---------------------------------------------------------------- 引擎进程
let proc = null;
let pending = null; // 当前等待回复的命令
let chain = Promise.resolve(); // 命令串行队列
let booted = false;
let engineInfo = { name: "", author: "" };
let lastError = "";
let switching = false; // 模型切换期间主动杀死旧进程，禁止 exit 自动重启

function startEngine() {
  if (proc) return;
  if (!fs.existsSync(EXE)) {
    lastError = "找不到引擎：" + EXE;
    console.error("[engine] " + lastError);
    return;
  }
  console.log("[engine] 启动 " + EXE);
  const me = spawn(EXE, [], { cwd: path.dirname(EXE), windowsHide: true });
  proc = me;
  me.stdout.setEncoding("utf8");
  me.stderr.setEncoding("utf8");
  me.stdin.setDefaultEncoding("utf8");

  let obuf = "";
  me.stdout.on("data", (d) => {
    if (proc !== me) return; // 旧进程迟到的输出不能污染新引擎的协议
    obuf += d;
    let i;
    while ((i = obuf.indexOf("\n")) >= 0) {
      const line = obuf.slice(0, i).replace(/\r$/, "");
      obuf = obuf.slice(i + 1);
      onStdout(line);
    }
  });

  let ebuf = "";
  me.stderr.on("data", (d) => {
    if (proc !== me) return;
    ebuf += d;
    let i;
    while ((i = ebuf.indexOf("\n")) >= 0) {
      const line = ebuf.slice(0, i).replace(/\r$/, "");
      ebuf = ebuf.slice(i + 1);
      onStderr(line);
    }
  });

  me.on("exit", (code) => {
    if (proc !== me) return; // 已被新进程替换：旧进程的 exit 不应清状态/触发重启
    console.log("[engine] 退出 code=" + code);
    proc = null;
    booted = false;
    if (pending) {
      clearTimeout(pending.timer);
      pending.reject(new Error("引擎进程退出 (code " + code + ")"));
      pending = null;
    }
    broadcast({ type: "engine", ok: false, msg: "引擎已退出" });
    if (switching) return; // 模型切换：旧进程退出是预期行为，等 /api/model 启动新进程
    setTimeout(() => {
      startEngine();
      boot().catch((e) => console.error("[engine] 重启失败 " + e.message));
    }, 400);
  });

  me.on("error", (e) => {
    if (proc !== me) return;
    lastError = e.message;
    console.error("[engine] spawn 失败 " + e.message);
    broadcast({ type: "engine", ok: false, msg: "spawn 失败：" + e.message });
  });
}

function onStderr(line) {
  if (!line) return;
  if (line.startsWith("info depth")) {
    // info depth 6 score 59 nodes 11031 time 27 nps 408555
    const m = {};
    const re = /(\w+)\s+(-?\d+)/g;
    let x;
    while ((x = re.exec(line))) m[x[1]] = Number(x[2]);
    if (m.depth) {
      broadcast({ type: "info", ...m });
    }
    return;
  }
  if (line.startsWith("info string")) {
    broadcast({ type: "log", msg: line.slice(12).trim() });
    return;
  }
  broadcast({ type: "log", msg: line });
}

function onStdout(line) {
  if (!line) return;
  if (line === "uciok") {
    finish({ kind: "uci" });
    return;
  }
  if (line === "readyok") {
    finish({ kind: "ready" });
    return;
  }
  if (line.startsWith("id name ")) engineInfo.name = line.slice(8);
  else if (line.startsWith("id author ")) engineInfo.author = line.slice(10);
  else if (line.startsWith("bestmove ")) finish({ kind: "go", bestmove: line.slice(9).trim() });
  else if (pending) {
    pending.lines.push(line); // eval / perft / fen / d 的裸输出
    // eval 与 perft 只回一行裸值、没有 readyok，收到即完成
    if (pending.kind === "eval" || pending.kind === "perft") finish({ kind: pending.kind });
  }
}

function finish(r) {
  if (!pending) return;
  const p = pending;
  pending = null;
  clearTimeout(p.timer);
  if (p.kind === r.kind || r.kind === undefined) p.resolve({ ...r, lines: p.lines });
  else p.reject(new Error("协议错位：期望 " + p.kind + "，收到 " + r.kind));
}

/* 发一条命令并等它的回复。kind 决定什么时候算完成。 */
function send(cmd, kind, timeoutMs) {
  return new Promise((resolve, reject) => {
    if (!proc) return reject(new Error(lastError || "引擎未启动"));
    const timer = setTimeout(() => {
      if (pending && pending.resolve === resolve) {
        pending = null;
        broadcast({ type: "log", msg: "命令超时：" + cmd });
        reject(new Error("引擎命令超时：" + cmd));
      }
    }, timeoutMs || 20000);
    pending = { kind, resolve, reject, lines: [], timer };
    try {
      proc.stdin.write(cmd + "\n");
    } catch (e) {
      clearTimeout(timer);
      pending = null;
      reject(e);
    }
  });
}

async function boot() {
  await send("uci", "uci", 8000);
  await send("isready", "ready", 8000);
  booted = true;
  console.log("[engine] 就绪 " + engineInfo.name);
  broadcast({ type: "engine", ok: true, name: engineInfo.name, author: engineInfo.author });
}

/* 只写不等回复的命令（position / ucinewgame 这类没有回执） */
function raw(cmd) {
  if (!proc) throw new Error(lastError || "引擎未启动");
  proc.stdin.write(cmd + "\n");
}

/* 设置局面：position 没有回执，靠紧随其后的 isready 确认已生效 */
async function setPos(moves) {
  raw(posCmd(moves));
  await send("isready", "ready", 8000);
}

function enqueue(fn) {
  const r = chain.then(fn, fn);
  chain = r.catch(() => {});
  return r;
}

function posCmd(moves) {
  const mv = (moves || []).filter((m) => /^[a-i][0-9][a-i][0-9]$/.test(m));
  return "position startpos" + (mv.length ? " moves " + mv.join(" ") : "");
}

/* ---------------------------------------------------------------- 模型切换 */
/* 模型权重编译在 exe 内，所以“换模型”就是换引擎可执行文件。
   只允许 PROJECT_ROOT 根目录和 dist/<版本>/ 下的 .exe，避免任意路径执行。 */
function listModelFiles() {
  const out = [];
  const add = (abs) => {
    if (!abs.toLowerCase().endsWith(".exe")) return;
    /* 只列 CatChess 发行版；xq*.exe / t_*.exe 是实验或诊断程序，误切会破坏服务 */
    if (!/^CatChess[-_.]/i.test(path.basename(abs))) return;
    const rel = path.relative(PROJECT_ROOT, abs).replace(/\\/g, "/");
    if (out.some((m) => m.path === abs)) return;
    out.push({ name: path.basename(abs), rel, path: abs });
  };
  for (const ent of fs.readdirSync(PROJECT_ROOT, { withFileTypes: true })) {
    if (ent.isFile()) add(path.join(PROJECT_ROOT, ent.name));
  }
  const dist = path.join(PROJECT_ROOT, "dist");
  if (fs.existsSync(dist)) {
    for (const ent of fs.readdirSync(dist, { withFileTypes: true })) {
      if (!ent.isDirectory() || ent.name.startsWith("_")) continue;
      const dir = path.join(dist, ent.name);
      for (const sub of fs.readdirSync(dir, { withFileTypes: true })) {
        if (sub.isFile()) add(path.join(dir, sub.name));
      }
    }
  }
  return out.sort((a, b) => a.rel.localeCompare(b.rel));
}

function findModel(nameOrRel) {
  const key = String(nameOrRel || "").replace(/\\/g, "/");
  return listModelFiles().find((m) => m.rel === key || m.name === key);
}

async function switchEngine(target) {
  return enqueue(async () => {
    const oldExe = EXE;
    const old = proc;
    switching = true;
    try {
      if (old) {
        await new Promise((resolve) => {
          let done = false;
          const finish = () => {
            if (done) return;
            done = true;
            resolve();
          };
          old.once("exit", finish);
          try { old.stdin.write("quit\n"); } catch (e) {}
          /* 个别版本对 quit 响应慢；1.5s 后强杀，避免切换卡死 */
          setTimeout(() => {
            try { old.kill(); } catch (e) {}
            finish();
          }, 1500);
        });
      }
    } finally {
      switching = false;
    }
    proc = null;
    booted = false;
    lastError = "";
    EXE = target.path;
    engineInfo = { name: "", author: "" };
    startEngine();
    if (!proc) throw new Error(lastError || "新模型启动失败");
    try {
      await boot();
    } catch (e) {
      /* 新模型握手失败：先杀掉残留的新进程，再恢复旧引擎，避免 startEngine() 看到 proc 非空直接返回 */
      try { if (proc) proc.kill(); } catch (_) {}
      proc = null;
      EXE = oldExe;
      engineInfo = { name: "", author: "" };
      booted = false;
      startEngine();
      try { await boot(); } catch (_) {}
      throw e;
    }
    return { exe: EXE, model: target.rel, name: engineInfo.name };
  });
}

// ---------------------------------------------------------------- HTTP
function readBody(req) {
  return new Promise((resolve, reject) => {
    let b = "";
    req.on("data", (d) => {
      b += d;
      if (b.length > 1e6) reject(new Error("body too large"));
    });
    req.on("end", () => {
      try {
        resolve(b ? JSON.parse(b) : {});
      } catch (e) {
        reject(e);
      }
    });
  });
}

function json(res, code, obj) {
  const s = JSON.stringify(obj);
  res.writeHead(code, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(s);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const p = url.pathname;

  if (p === "/api/stream") {
    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });
    res.write(": connected\n\n");
    clients.add(res);
    if (booted) res.write("data: " + JSON.stringify({ type: "engine", ok: true, ...engineInfo }) + "\n\n");
    const ka = setInterval(() => {
      try {
        res.write(": ka\n\n");
      } catch (e) {}
    }, 15000);
    req.on("close", () => {
      clearInterval(ka);
      clients.delete(res);
    });
    return;
  }

  if (p === "/api/status") {
    return json(res, 200, {
      ok: booted && !!proc,
      name: engineInfo.name,
      author: engineInfo.author,
      exe: EXE,
      error: lastError,
    });
  }

  if (p === "/api/models") {
    return json(res, 200, {
      ok: true,
      current: EXE,
      models: listModelFiles().map((m) => ({
        name: m.name,
        rel: m.rel,
        current: path.resolve(m.path) === path.resolve(EXE),
      })),
    });
  }

  if (p === "/api/model" && req.method === "POST") {
    try {
      const body = await readBody(req);
      const target = findModel(body.name || body.exe || "");
      if (!target) return json(res, 400, { ok: false, error: "模型不在允许列表内" });
      const out = await switchEngine(target);
      broadcast({ type: "engine", ok: true, name: out.name || "CatChess" });
      return json(res, 200, { ok: true, ...out });
    } catch (e) {
      return json(res, 500, { ok: false, error: e.message });
    }
  }

  if (p === "/api/think" && req.method === "POST") {
    try {
      const body = await readBody(req);
      const ms = Math.max(30, Math.min(20000, Number(body.ms) || 600));
      const out = await enqueue(async () => {
        if (!booted) throw new Error("引擎未就绪");
        await setPos(body.moves);
        return send("go movetime " + ms, "go", ms + 30000);
      });
      return json(res, 200, { ok: true, bestmove: out.bestmove, ms });
    } catch (e) {
      return json(res, 500, { ok: false, error: e.message });
    }
  }

  if (p === "/api/eval" && req.method === "POST") {
    try {
      const body = await readBody(req);
      const out = await enqueue(async () => {
        if (!booted) throw new Error("引擎未就绪");
        await setPos(body.moves);
        return send("eval", "eval", 8000);
      });
      return json(res, 200, { ok: true, cp: Number(out.lines[0]) });
    } catch (e) {
      return json(res, 500, { ok: false, error: e.message });
    }
  }

  if (p === "/api/perft" && req.method === "POST") {
    try {
      const body = await readBody(req);
      const depth = Math.max(1, Math.min(4, Number(body.depth) || 3));
      const out = await enqueue(async () => {
        if (!booted) throw new Error("引擎未就绪");
        await setPos(body.moves);
        return send("perft " + depth, "perft", 30000);
      });
      return json(res, 200, { ok: true, nodes: Number(out.lines[0]) });
    } catch (e) {
      return json(res, 500, { ok: false, error: e.message });
    }
  }

  if (p === "/api/newgame" && req.method === "POST") {
    try {
      await enqueue(async () => {
        if (!booted) throw new Error("引擎未就绪");
        raw("ucinewgame");
        await send("isready", "ready", 8000);
      });
      return json(res, 200, { ok: true });
    } catch (e) {
      return json(res, 500, { ok: false, error: e.message });
    }
  }

  // 静态文件
  let rel = p === "/" ? "/index.html" : p;
  const file = path.join(ROOT, path.normalize(rel).replace(/^([/\\])+/, ""));
  if (!file.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end("forbidden");
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      return res.end("404 " + p);
    }
    res.writeHead(200, {
      "Content-Type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(data);
  });
});

startEngine();
if (proc) boot().catch((e) => console.error("[engine] 握手失败 " + e.message));

server.listen(PORT, "127.0.0.1", () => {
  console.log("CatChess 前端已启动: http://127.0.0.1:" + PORT);
  console.log("引擎: " + EXE);
});

process.on("SIGINT", () => {
  if (proc) {
    try {
      proc.stdin.write("quit\n");
    } catch (e) {}
    setTimeout(() => process.exit(0), 200);
  } else process.exit(0);
});
