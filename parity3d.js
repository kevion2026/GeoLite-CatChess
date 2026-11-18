const fs = require("fs");
const E = require("./engine3d.js");
E.setModel(JSON.parse(fs.readFileSync("model3d.json", "utf8")));
const cases = JSON.parse(fs.readFileSync("data/parity3d.json", "utf8"));
let maxDiff = 0, maxAt = null;
for (const c of cases) {
  for (let layer = 0; layer < c.layers.length; layer++) {
    const js = E.geometry(Int8Array.from(c.board), c.side, layer, layer).state;
    const py = c.layers[layer];
    for (let i = 0; i < py.length; i++) {
      const d = Math.abs(js[i] - py[i]);
      if (d > maxDiff) { maxDiff = d; maxAt = { layer, i, js: js[i], py: py[i] }; }
    }
  }
}
console.log("max |diff| =", maxDiff.toFixed(6), "| at", JSON.stringify(maxAt));
