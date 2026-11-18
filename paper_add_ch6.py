"""在论文中插入第 6 章：三维立体化与双路线仲裁，并把原 6/7 章顺延。"""

import pathlib

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TARGET = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋引擎技术论文.docx")
CN, HEI, EN = "宋体", "黑体", "Times New Roman"

doc = Document(str(TARGET))


def set_font(run, cn=CN, en=EN, size=10.5, bold=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = en
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), en)
    rfonts.set(qn("w:hAnsi"), en)
    run.font.color.rgb = RGBColor(0, 0, 0)


def body(text, size=10.5):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.first_line_indent = Pt(size * 2)
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    set_font(p.add_run(text), size=size)
    return p


def head1(text):
    p = doc.add_paragraph(style="Heading 1")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_font(p.add_run(text), HEI, EN, 12, True)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    return p


def head2(text):
    p = doc.add_paragraph(style="Heading 2")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_font(p.add_run(text), HEI, EN, 10.5, True)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    return p


def caption(text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.0
    set_font(p.add_run(text), HEI, EN, 9, False)
    p.paragraph_format.keep_with_next = True
    return p


def cell_border(cell, edges, sz=6):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge in edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:color"), "000000")
        borders.append(el)


def add_table(headers, rows, widths, note=None, size=9):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl._tbl.tblPr.append(layout)
    trPr = tbl.rows[0]._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))
    trPr.append(OxmlElement("w:cantSplit"))
    for i, h in enumerate(headers):
        c = tbl.rows[0].cells[i]
        c.width = Cm(widths[i])
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.first_line_indent = Pt(0)
        set_font(p.add_run(h), CN, EN, size, True)
        cell_border(c, ["top"], 12)
        cell_border(c, ["bottom"], 6)
    for row in rows:
        tr = tbl.add_row()
        tr._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for i, v in enumerate(row):
            c = tr.cells[i]
            c.width = Cm(widths[i])
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 else WD_ALIGN_PARAGRAPH.RIGHT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            set_font(p.add_run(str(v)), CN, EN, size, False)
    for c in tbl.rows[-1].cells:
        cell_border(c, ["bottom"], 12)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.0
    if note:
        set_font(p.add_run(note), CN, EN, 9)
    return tbl


blocks = []


def P(fn, *a, **k):
    blocks.append(fn(*a, **k)._p)


def T(fn, *a, **k):
    blocks.append(fn(*a, **k)._tbl)


# ---------------------------------------------------------------- 第 6 章正文
P(head1, "6　三维立体化与双路线仲裁")

P(head2, "6.1　从一张点云到三张点云")
P(body, "单一共现矩阵把两类完全不同的关系混在同一张表里：一类是九宫附近的贴身纠缠，另一类隔着半盘的长距离威慑。"
        "对一张混表做一次截断奇异值分解，只能得到一条主轴，主轴方向被两类关系平均掉，既不指向连环马，也不指向沉底车。"
        "因此本文把共现关系拆成三个窗口分别建表：邻域窗口取切比雪夫距离不超过 2 的令牌对，权 1.0；"
        "共线窗口取同一横线或竖线且距离不超过 6 的对，权 0.5；中距窗口取距离 3 至 5 的对，并对跨区同兵种再给 0.6。"
        "三张矩阵各自做正点互信息与截断奇异值分解，各取前三维，令牌因此在三个三维空间里各有一个坐标。")

P(head2, "6.2　状态、压缩与双端一致")
P(body, "在每个空间内，局面仍按加权质心、协方差主特征向量与垂直残差合成 7 维状态，三空间拼接为 21 维。"
        "压缩规则改为按三个空间垂直距离的平方和选弃：每层删去在三张点云里总偏离最大的那个令牌，"
        "被删的令牌在三张图里同时消失，三条主线始终是线。为让网页端与训练端给出同一结果，"
        "主特征向量用幂迭代求解并迭代 160 次；与 numpy 的特征分解相比，24 个抽样局面的最大分量偏差为 0.000000。")

P(head2, "6.3　三个空间的判别能力")
P(body, "按同一协议在 19999 个分层抽样局面上做五折交叉验证，结果见表5。中距空间单独就达到 61.46%，"
        "反而高于共线空间的 57.28%；三空间联合 62.94%，比双三维的 62.58% 只高 0.36 个百分点，"
        "比单三维的 61.63% 高 1.31 个百分点。这个幅度说明：三张点云仍然高度同源，"
        "拆表带来的不是新信息，而是对同一批点云的三种投影。")
P(caption, "表5　三个三维空间的奇异值与判别能力")
T(add_table, ["空间", "窗口规则", "前三奇异值", "单独 kNN", "联合 kNN"],
  [["邻域", "切比雪夫≤2，权 1.0", "225.99 / 182.79 / 164.66", "60.10%", "62.94%（第 5 层）"],
   ["共线", "同线≤6，权 0.5", "224.05 / 131.08 / 117.97", "57.28%", "同上"],
   ["中距", "3~5 格，同兵种 0.6", "314.53 / 115.77 / 95.24", "61.46%", "同上"],
   ["参照", "二维 4 维 / 单三维 7 维 / 双三维 14 维", "—", "56.43% / 61.63% / 62.58%", "—"]],
  [2.2, 5.2, 4.4, 2.6, 3.0],
  "注：评估集 19999 个局面，令牌 692 个，多数类 32.87%；“单独”指只用该空间 7 维状态的 k 近邻判别。")

P(head2, "6.4　两条引力路线与第三空间仲裁")
P(body, "选着不再依赖搜索，而是两条互不相干的引力路线各自出一手。局部路线按邻域点云计算：己方质量对敌王的吸引、"
        "己方令牌两两靠近形成的密集度（连环马、担子炮、士象联防都表现为高密度核心簇）、以及被攻击且无保护的暴露惩罚。"
        "全局路线按共线点云计算：车与炮沿横竖线的机动格数、占据中路、过河与纵深、敌方重子对本方九宫的远程压迫。"
        "两条路线各取势最高的一手，得到两个候选着法。")
P(body, "第三个三维空间不参与选着，只承担仲裁：把两个候选着法各自走完后的中距点云状态喂给一个打分模型，分高者执行，"
        "并设一个门限，分差过小时退回两空间各自的胜率比较，避免在噪声上反复横跳。"
        "初始局面实测：局部候选为马二进三、全局候选为炮二平一，仲裁后取局部。")

P(head2, "6.5　云库评分：为判断胜率另找数据")
P(body, "棋谱胜负是稀疏标签：一个局面只在整局结束时才得到一个标签，且大量和棋使三类标签严重偏斜，"
        "此前的四维状态与令牌词袋实验分别只到 49.0% 与 57.5%。本文改用外部引擎评分作监督信号："
        "局面转成标准中国象棋记谱格式后向象棋云库的评分接口查询，取得走子方视角的分值。"
        "共请求 6000 个真实棋谱局面，命中 5591 个，命中率 93.5%；云库用 ±29999 标记必杀局面，剔除 57 个后余 5534 个，"
        "分值截断到 ±1500 厘兵。这样每个局面都有一条连续的分值，标签密度远高于胜负标签。")
P(body, "把 21 维几何状态、9 个形特征（密集度、延伸、主轴斜率各三组）与 9 个子力结构特征分别组合做岭回归，结果见表6。"
        "只用几何时 R² 为 0.04、Spearman 0.16，几乎不能解释分值；加上子力结构后 R² 升到 0.21、平均绝对误差 190 厘兵、"
        "Spearman 0.36，三类判别 71.7%（多数类 64.3%）。提分主要来自子力，几何只补形状。")
P(caption, "表6　云库评分的回归实验（5534 个局面）")
T(add_table, ["特征组", "分值 MAE（厘兵）", "R²", "Spearman", "三类准确率"],
  [["邻域 7 维", "201", "0.04", "0.14", "65.2%"],
   ["共线 7 维", "202", "0.03", "0.12", "65.9%"],
   ["中距 7 维", "202", "0.00", "0.04", "64.8%"],
   ["三空间 21 维", "202", "0.04", "0.16", "66.7%"],
   ["21 维 + 9 形特征", "203", "0.04", "0.16", "67.1%"],
   ["21 维 + 9 形 + 9 子力", "190", "0.21", "0.36", "71.7%"],
   ["仅 9 子力", "192", "0.17", "0.33", "67.3%"]],
  [4.6, 3.4, 1.6, 2.2, 2.6],
  "注：三类按 |分值|≥150 厘兵划分胜负、其余为和，多数类 64.3%；量化留出 25%，随机种子固定。")

P(head2, "6.6　裁决方式的实战差异")
P(body, "把不同裁决依据分别接进引擎做自对弈，每步只比较一层势，没有任何搜索树，结果见表7。"
        "双三维方案只比两空间胜率，能走满 240 手、22 次吃子、单步 0.9 毫秒；"
        "换成第三空间仲裁后 56 手即被将死，吃子降到 2 次；改用云库评分模型裁决，240 手走满、18 次吃子、单步 1.8 毫秒；"
        "而把云库门限抬到 60 厘兵，反而 167 手被将死。可见仲裁器本身若近似随机，接管决策就是净损失；"
        "只有监督信号足够可靠，第三空间才有意义。")
P(caption, "表7　三种裁决依据下的自对弈表现")
T(add_table, ["裁决依据", "门限", "手数", "吃子", "单步耗时"],
  [["双三维，仅本空间胜率", "—", "240（走满）", "22", "0.9 ms"],
   ["三空间，第三空间仲裁", "0", "56（被将死）", "2", "1.2 ms"],
   ["三空间，云库评分模型", "0", "240（走满）", "18", "1.8 ms"],
   ["三空间，云库评分模型", "60 厘兵", "167（被将死）", "12", "1.2 ms"]],
  [4.6, 2.4, 3.0, 1.6, 2.8],
  "注：红黑同引擎自对弈，上限 240 手；难度噪声为 0，重复局面按哈希惩罚。")

P(head2, "6.7　讨论：形状与形势的分界")
P(body, "三个空间把“棋子怎么聚、线怎么伸”描述得足够清楚：中距空间单独就有 61.46% 的态势判别，"
        "已经超过了最初的二维方案 5 个百分点。但同一条链路在预测分值上只有 0.04 的解释力，"
        "而分值几乎由子力差与兵种结构决定——几何状态里根本没有子力这一项。"
        "这就把职责边界划清了：几何适合做路由，负责判断“现在该贴身还是该拉开”，不适合做形势判别。"
        "立体化、拆窗口、加仲裁，都没有改变这一点，只是把它从一次实验变成了三次独立验证。")

# ---------------------------------------------------------------- 插入与重编号
anchor = None
for p in doc.paragraphs:
    if p.text.strip().startswith("6\u3000讨论"):
        anchor = p
        break
if anchor is None:
    raise SystemExit("找不到 6　讨论 标题")

for el in blocks:
    anchor._p.addprevious(el)

for p in doc.paragraphs:
    txt = p.text.strip()
    if txt == "6\u3000讨论":
        if p.runs:
            p.runs[0].text = "7\u3000讨论"
            for r in p.runs[1:]:
                r.text = ""
    elif txt == "7\u3000结论":
        if p.runs:
            p.runs[0].text = "8\u3000结论"
            for r in p.runs[1:]:
                r.text = ""

doc.save(str(TARGET))
print("第 6 章已插入，原讨论、结论顺延为 7、8")
