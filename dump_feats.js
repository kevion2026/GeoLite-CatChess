// 从 stdin 逐行读 {"b":[...],"s":1}，输出 45 维特征，供 Python 端对拍
global.MODEL3D = JSON.parse(require("fs").readFileSync("model_triple.json", "utf8"));
const E = require("./engine3d.js");
E.setModel(global.MODEL3D);
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin });
const seg = global.MODEL3D.tree.model;
rl.on("line", (line) => {
  if (!line.trim()) return;
  const req = JSON.parse(line);
  const g = E.geometry(req.b, req.s, 0, 0);
  const feats = g.state.concat(E.shapeOf(g.a.state, g.a.tokens))
    .concat(E.shapeOf(g.b.state, g.b.tokens)).concat(E.shapeOf(g.c.state, g.c.tokens));
  for (const v of E.matFeats(req.b, req.s)) feats.push(v);
  for (const v of E.threatFeats(req.b, req.s)) feats.push(v);
  process.stdout.write(JSON.stringify(feats) + "\n");
});
