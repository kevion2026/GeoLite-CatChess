/* 开发用：CDP 驱动 headless Edge，验证交互并截图。不参与产品运行。 */
"use strict";
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const PORT = 9333;
const OUT = process.argv[2] || "C:/Users/kevion/AppData/Local/Temp/wbshot/play.png";
const URL_PAGE = process.argv[3] || "http://127.0.0.1:8770/";
const SCRIPT = process.argv[4] || "";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function getJson(path) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
      let b = "";
      res.on("data", (d) => (b += d));
      res.on("end", () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
    }).on("error", reject);
  });
}

(async function () {
  fs.mkdirSync("C:/Users/kevion/AppData/Local/Temp/wbshot/prof3", { recursive: true });
  const proc = spawn(EDGE, [
    "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
    "--window-size=" + (process.env.WSIZE || "1600,1080"),
    "--remote-debugging-port=" + PORT,
    "--user-data-dir=C:/Users/kevion/AppData/Local/Temp/wbshot/prof3",
    "--no-first-run", "--no-default-browser-check",
    URL_PAGE
  ], { stdio: "ignore" });

  // 等调试端口
  let ver = null;
  for (let i = 0; i < 60; i++) {
    try { ver = await getJson("/json/version"); break; } catch (e) { await sleep(250); }
  }
  if (!ver) { console.error("调试端口未就绪"); proc.kill(); process.exit(1); }

  const list = await getJson("/json/list");
  const page = list.find((t) => t.type === "page" && t.url.includes("127.0.0.1"));
  if (!page) { console.error("没有找到页面 target", list.map(x => x.url)); proc.kill(); process.exit(1); }

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const waiters = new Map();
  const logs = [];
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && waiters.has(m.id)) { waiters.get(m.id)(m); waiters.delete(m.id); }
    if (m.method === "Runtime.consoleAPICalled") {
      logs.push(m.params.type + ": " + m.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
    }
    if (m.method === "Runtime.exceptionThrown") {
      logs.push("EXCEPTION: " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    }
  });
  const send = (method, params) => new Promise((res) => {
    const i = ++id;
    waiters.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
  });

  await new Promise((r) => ws.addEventListener("open", r));
  await send("Runtime.enable");
  await send("Page.enable");
  await sleep(2200);

  if (SCRIPT) {
    const r = await send("Runtime.evaluate", { expression: SCRIPT, awaitPromise: true, returnByValue: true });
    const v = r.result?.result?.value;
    if (v !== undefined) console.log("eval →", JSON.stringify(v));
    if (r.result?.exceptionDetails) console.log("eval 异常:", JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  }

  await sleep(Number(process.env.SHOT_WAIT || 2600));

  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  if (shot.result?.data) {
    fs.writeFileSync(OUT, Buffer.from(shot.result.data, "base64"));
    console.log("截图 →", OUT);
  } else {
    console.log("截图失败", JSON.stringify(shot).slice(0, 300));
  }
  if (logs.length) console.log("--- 控制台 ---\n" + logs.join("\n"));
  else console.log("控制台无输出");

  proc.kill();
  await sleep(300);
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
