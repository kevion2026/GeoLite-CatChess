"""生成 Pikafish 棋艺测评报告（单文件 HTML，无外链）。"""

import json
import pathlib

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
OUT = HERE / "GeoLite象棋_Pikafish测评.html"

CONFIGS = [
    ("nodes:200", "200 节点", "nodes_200"),
    ("nodes:1000", "1000 节点", "nodes_1000"),
    ("depth:1", "深度 1", "depth_1"),
    ("movetime:100", "每步 100 ms", "movetime_100"),
]

rows = []
for limit, label, fname in CONFIGS:
    p = HERE / "data" / f"pikafish_match_{fname}.json"
    if not p.exists():
        continue
    d = json.loads(p.read_text(encoding="utf-8"))
    rs = d["rows"]
    w = sum(1 for r in rs if r["res"] == "win")
    dr = sum(1 for r in rs if r["res"] == "draw")
    l = sum(1 for r in rs if r["res"] == "loss")
    rows.append(dict(label=label, limit=limit, n=len(rs), w=w, d=dr, l=l,
                     plies=round(sum(r["plies"] for r in rs) / len(rs), 1),
                     caps=round(sum(r["caps"] for r in rs) / len(rs), 1),
                     ms=round(sum(r["our_ms"] for r in rs) / len(rs), 1),
                     all=rs))

total = dict(n=sum(r["n"] for r in rows), w=sum(r["w"] for r in rows),
             d=sum(r["d"] for r in rows), l=sum(r["l"] for r in rows))

bars = ""
for r in rows:
    h = int(r["plies"] / 60 * 150)
    bars += (f'<g><rect x="0" y="{170 - h}" width="46" height="{h}" rx="4" fill="#3f6b8f"/>'
             f'<text x="23" y="188" text-anchor="middle" font-size="11" fill="#5c6b7a">{r["plies"]}</text>'
             f'<text x="23" y="204" text-anchor="middle" font-size="10" fill="#8a97a3">{r["label"]}</text></g>')
bars = bars.replace('x="0" ', 'x="0" ', 1)
# 手工平移每组
shifted = ""
for i, r in enumerate(rows):
    h = int(r["plies"] / 60 * 150)
    x = 20 + i * 90
    shifted += (f'<g><rect x="{x}" y="{170 - h}" width="52" height="{h}" rx="5" fill="#3f6b8f"/>'
                f'<text x="{x + 26}" y="{170 - h - 8}" text-anchor="middle" font-size="12" fill="#26323c">{r["plies"]}</text>'
                f'<text x="{x + 26}" y="190" text-anchor="middle" font-size="11" fill="#5c6b7a">{r["label"]}</text>'
                f'<text x="{x + 26}" y="206" text-anchor="middle" font-size="10" fill="#8a97a3">'
                f'{r["w"]}-{r["d"]}-{r["l"]}</text></g>')

trs = ""
for r in rows:
    trs += (f"<tr><td>{r['label']}</td><td class='n'>{r['n']}</td>"
            f"<td class='n'>{r['w']} - {r['d']} - {r['l']}</td>"
            f"<td class='n'>{r['plies']}</td><td class='n'>{r['caps']}</td>"
            f"<td class='n'>{r['ms']} ms</td></tr>")

game_rows = ""
for r in rows:
    for g in r["all"]:
        res = {"win": "胜", "draw": "和", "loss": "负"}.get(g["res"], g["res"])
        game_rows += (f"<tr><td>{r['label']}</td><td class='n'>{g['game']}</td>"
                      f"<td>{ '红' if g['ours_side']=='red' else '黑' }</td>"
                      f"<td class='n'>{g['plies']}</td><td class='n'>{g['caps']}</td>"
                      f"<td class='n'>{g['our_ms']} ms</td><td class='n'>{res}</td></tr>")

html = f"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<title>GeoLite 棋艺测评 · Pikafish</title>
<style>
:root {{ --ink:#1f2a33; --muted:#66727d; --line:#dfe6ec; --bg:#f7f9fb; --accent:#3f6b8f; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.7 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif; }}
main {{ max-width:980px; margin:0 auto; padding:48px 28px 72px; }}
h1 {{ font-size:26px; margin:0 0 6px; letter-spacing:.5px; }}
.sub {{ color:var(--muted); font-size:13px; margin-bottom:34px; }}
h2 {{ font-size:17px; margin:38px 0 10px; padding-left:10px; border-left:3px solid var(--accent); }}
p {{ margin:8px 0; }}
.card {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:22px 24px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:22px 0 6px; }}
.kpi {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px 18px; }}
.kpi b {{ display:block; font-size:26px; font-weight:600; letter-spacing:.5px; }}
.kpi span {{ color:var(--muted); font-size:12px; }}
table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13.5px;
  border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
th,td {{ padding:9px 12px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ background:#eef3f7; font-weight:600; font-size:12.5px; color:#33414d; }}
td.n,th.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
tr:last-child td {{ border-bottom:none; }}
.chart {{ background:#fff; border:1px solid var(--line); border-radius:12px; padding:16px 10px 8px; }}
.note {{ color:var(--muted); font-size:12.5px; margin-top:8px; }}
.tag {{ display:inline-block; padding:1px 8px; border:1px solid var(--line); border-radius:999px;
  font-size:12px; color:var(--muted); background:#fff; margin-right:6px; }}
ul {{ margin:8px 0 0 18px; padding:0; }}
li {{ margin:5px 0; }}
</style>
<main>
  <h1>GeoLite 象棋引擎 · 棋艺测评</h1>
  <div class="sub">
    <span class="tag">参照引擎 Pikafish 2026-09-06</span>
    <span class="tag">Windows x86-64</span>
    <span class="tag">NNUE 48.4 MB</span>
    <span class="tag">UCI 直连对局</span>
    <span class="tag">被测版本 三空间 + 分支激活树</span>
  </div>

  <div class="kpis">
    <div class="kpi"><b>{total['n']}</b><span>总对局</span></div>
    <div class="kpi"><b>{total['w']} / {total['d']} / {total['l']}</b><span>胜 / 和 / 负</span></div>
    <div class="kpi"><b>{rows[0]['plies'] if rows else '—'}</b><span>200 节点档平均手数</span></div>
    <div class="kpi"><b>{rows[0]['ms'] if rows else '—'} ms</b><span>我方单步耗时</span></div>
  </div>

  <h2>一、测评方法</h2>
  <div class="card">
    <p>被测引擎以纯几何链路出着：三张点云各取三维，21 维状态加形与子力特征，由 24 分支激活树给出形势分，
    局部与全局两条引力路线各出一手，第三空间仲裁定方向；方向内再由动态分支树展开候选着（宽 3、对手回应宽 1），
    取符合度最高的一步。静态库扩到 3000 个分层状态。整个过程没有 α-β 剪枝，单步 4 至 9 毫秒。</p>
    <p>参照方为 Pikafish 官方 2026-09-06 发布包（Windows x86-64，配套 pikafish.nnue）。对局通过 UCI 协议直连，
    每方轮流执红黑；为避免两段确定性引擎反复下出同一盘棋，开局前 4 着随机走子，其后完全由引擎自行决策。
    单局上限 240 着，同一局面出现三次判和；无合法着法判负。</p>
  </div>

  <h2>二、四档强度结果</h2>
  <table>
    <thead><tr><th>Pikafish 档位</th><th class="n">局数</th><th class="n">胜-和-负</th>
    <th class="n">平均手数</th><th class="n">平均吃子</th><th class="n">我方单步</th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
  <p class="note">“节点”指每步搜索节点上限；深度 1 为只搜一层；每步 100 ms 为时间限制。三档均强于被测引擎。</p>

  <h2>三、平均手数分布</h2>
  <div class="chart">
    <svg width="100%" height="230" viewBox="0 0 400 230" preserveAspectRatio="xMidYMid meet">
      <line x1="12" y1="170" x2="386" y2="170" stroke="#dfe6ec"/>
      {shifted}
    </svg>
  </div>

  <h2>四、逐局记录</h2>
  <table>
    <thead><tr><th>档位</th><th class="n">局</th><th>执子</th><th class="n">手数</th>
    <th class="n">吃子</th><th class="n">我方单步</th><th class="n">结果</th></tr></thead>
    <tbody>{game_rows}</tbody>
  </table>

  <h2>五、结论</h2>
  <div class="card">
    <ul>
      <li>四档合计 {total['n']} 局、{total['w']} 胜 {total['d']} 和 {total['l']} 负；
      200 节点档平均 {rows[0]['plies']} 手，1000 节点档平均 {rows[1]['plies'] if len(rows)>1 else '—'} 手。</li>
      <li>动态分支树把最弱档的对抗从平均 47 手延长到 {rows[0]['plies']} 手，深度 1 档出现 2 局和棋；
      但胜场仍为 0，说明“宽束两层的战术校验”只是延缓败局，不足以逆转。</li>
      <li>败因集中在战术层：没有搜索意味着吃子交换、将军与反将都不会预演，十几手之后就会连续丢子，平均每局被吃 7 个子。</li>
      <li>几何路由的判分能力（留出集 R² 0.21、三类 71.2%）只说明“形势判断比随机好”，
      不足以替代一层以上的战术校验；这正是本次测评给出的最硬结论。</li>
      <li>若要在不引入 α-β 搜索的前提下提升，务实的方向是给候选着法加一层“吃子与将军的即时校验分支”，
      即在激活树里增加战术叶子，而不是继续堆几何维度。</li>
      <li>参照引擎属于当代最强开源象棋引擎之一，200 节点已足以碾压入门级程序，因此 0 胜并不意外；
      该结果可作为“无搜索几何引擎”当前棋力上限的基线记录。</li>
    </ul>
  </div>
  <p class="note">测评脚本 match_pikafish.py；原始对局数据 data/pikafish_match_*.json。Pikafish 采用 GPL-3.0 许可，仅用于本地测评。</p>
</main>
</html>
"""
OUT.write_text(html, encoding="utf-8")
print("已生成", OUT, round(OUT.stat().st_size / 1024), "KB")
