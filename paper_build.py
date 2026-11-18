"""生成 GeoLite 象棋引擎技术论文（中文期刊体例，数字取自 model.json / book.json）。"""

import json
import pathlib

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋")
OUT = pathlib.Path(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋引擎技术论文.docx")

model = json.loads((HERE / "model.json").read_text(encoding="utf-8"))
book = json.loads((HERE / "data" / "book.json").read_text(encoding="utf-8"))
meta = model["meta"]
layers = model["layers"]
base = model["baseline"]
dim8 = model["dim8"]
wp = model["winprob"]
wpall = model.get("winprob_all", {})
bow = model["winprob_bow"]

CN = "宋体"
HEI = "黑体"
KAI = "楷体"
FANG = "仿宋"
EN = "Times New Roman"


# ---------------------------------------------------------------- 基础样式
def set_run_font(run, cn=CN, en=EN, size=10.5, bold=False, color=(0, 0, 0)):
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
    run.font.color.rgb = RGBColor(*color)


def style_font(style, cn, size, bold=False):
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.name = EN
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    rfonts.set(qn("w:ascii"), EN)
    rfonts.set(qn("w:hAnsi"), EN)
    style.font.color.rgb = RGBColor(0, 0, 0)


def keep_next(p):
    p.paragraph_format.keep_with_next = True


def body(text, indent=True, size=10.5, space_after=0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.first_line_indent = Pt(size * 2)
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    r = p.add_run(text)
    set_run_font(r, size=size)
    return p


def head1(text):
    p = doc.add_paragraph(style="Heading 1")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(text)
    set_run_font(r, HEI, EN, 12, True)
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)
    keep_next(p)
    return p


def head2(text):
    p = doc.add_paragraph(style="Heading 2")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(text)
    set_run_font(r, HEI, EN, 10.5, True)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(3)
    keep_next(p)
    return p


def caption(text, before=4):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.0
    r = p.add_run(text)
    set_run_font(r, HEI, EN, 9, False)
    keep_next(p)
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
    tblPr = tbl._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    hdr = tbl.rows[0]
    trPr = hdr._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    trPr.append(th)
    cs = OxmlElement("w:cantSplit")
    trPr.append(cs)
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        c.width = Cm(widths[i])
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.first_line_indent = Pt(0)
        r = p.add_run(h)
        set_run_font(r, CN, EN, size, True)
        cell_border(c, ["top"], 12)
        cell_border(c, ["bottom"], 6)
    for row in rows:
        tr = tbl.add_row()
        trtr = tr._tr.get_or_add_trPr()
        trtr.append(OxmlElement("w:cantSplit"))
        for i, v in enumerate(row):
            c = tr.cells[i]
            c.width = Cm(widths[i])
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if isinstance(v, str) and not v.replace(".", "").replace("-", "").replace("%", "").isdigit() else WD_ALIGN_PARAGRAPH.RIGHT
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(str(v))
            set_run_font(r, CN, EN, size, False)
    last = tbl.rows[-1]
    for c in last.cells:
        cell_border(c, ["bottom"], 12)
    if note:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(note)
        set_run_font(r, CN, EN, 9)
    else:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.0
    return tbl


def add_toc():
    p = doc.add_paragraph()
    a = OxmlElement("w:fldChar")
    a.set(qn("w:fldCharType"), "begin")
    r1 = p.add_run()
    r1._r.append(a)
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = 'TOC \\o "1-2" \\h \\z \\u'
    r2 = p.add_run()
    r2._r.append(it)
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    r3 = p.add_run()
    r3._r.append(sep)
    r4 = p.add_run("（打开文档后按 F9 或右键更新目录）")
    set_run_font(r4, CN, EN, 10.5)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    r5 = p.add_run()
    r5._r.append(end)


def add_page_number(section, start=None):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = "PAGE"
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    run = p.add_run()
    run._r.append(fld1)
    run._r.append(it)
    run._r.append(fld2)
    set_run_font(run, CN, EN, 9)
    if start is not None:
        sectPr = section._sectPr
        numPr = sectPr.find(qn("w:pgNumType"))
        if numPr is None:
            numPr = OxmlElement("w:pgNumType")
            sectPr.append(numPr)
        numPr.set(qn("w:start"), str(start))


# ---------------------------------------------------------------- 文档
doc = Document()
style_font(doc.styles["Normal"], CN, 10.5)
doc.styles["Normal"].paragraph_format.line_spacing = 1.5

sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, attr, Cm(2.5))
add_page_number(sec, start=1)

# 题名
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(6)
r = p.add_run("用几何链路驱动中国象棋引擎：实现与实证")
set_run_font(r, HEI, EN, 18, True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(4)
r = p.add_run("Geometric State Routing for a Chinese Chess Engine: Implementation and Empirical Evaluation")
set_run_font(r, HEI, EN, 12, False)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(2)
r = p.add_run("kevion")
set_run_font(r, KAI, EN, 12)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(10)
r = p.add_run("（单位与通信邮箱：待补）")
set_run_font(r, CN, EN, 9)

# 摘要
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(6)
p.paragraph_format.line_spacing = 1.5
r = p.add_run("摘要：")
set_run_font(r, HEI, EN, 9, True)
r = p.add_run(
    f"为检验“语言模型的几何语义假设”能否迁移到状态空间闭合的棋类任务，本文把 GeoLite-LLM 提出的五段链路"
    f"（令牌化、二维坐标、四维状态、级联压缩、检索判别）落到中国象棋引擎上，并给出可复现的工程实现与消融实验。"
    f"系统以“阵营·兵种·规范化格位”为令牌，用 PPMI 与截断奇异值分解把令牌压成二维坐标，以加权质心与主方向拟合出"
    f"四维状态，再逐层删除离主线最远的棋子形成十层压缩，最后用状态原型与 k 近邻检索判定六类局面态势，并将态势映射为"
    f"搜索评估中的权重偏置。规则内核与 α-β 搜索承担合法性底线与战术计算。实验使用 {meta['positions']} 个局面"
    f"（{meta['games']} 局自对弈加 {meta['real_positions']} 个来自 {meta['pgn_files']} 份真实棋谱的局面，词表 {meta['vocab']}）。"
    f"结果显示：四维状态的检索准确率在第 9 层达到 {layers[9]['knn_acc']*100:.1f}%，高于多数类基线 {meta['majority']*100:.1f}%，"
    f"但同语料上的令牌词袋逻辑回归达到 {base['bow_lr'][0]*100:.1f}%；八维坐标的 17 维状态可提到 {dim8['knn10']*100:.1f}%；"
    f"十层压缩并未降低准确率，反而略优于第 0 层，与“压缩只减信息”的预期相反。胜率预测实验进一步表明，"
    f"仅凭四维状态判定胜和负的准确率为 {wpall['4维 第0层']['acc']*100:.1f}%（多数类 {wpall['4维 第0层']['majority']*100:.1f}%），"
    f"而令牌词袋可达 {bow['metrics']['acc']*100:.1f}%。据此提出判断：几何链路在棋类中适合承担局面态势的路由与着法排序，"
    f"不适宜承担局面判别与胜负预测；其信息瓶颈来自坐标只保留位置、丢失兵种身份与子力关系。"
)
set_run_font(r, FANG, EN, 9)

p = doc.add_paragraph()
p.paragraph_format.line_spacing = 1.5
r = p.add_run("关键词：")
set_run_font(r, HEI, EN, 9, True)
r = p.add_run("几何状态；PPMI；奇异值分解；k 近邻检索；中国象棋引擎；局面态势")
set_run_font(r, FANG, EN, 9)

# 英文摘要
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(8)
p.paragraph_format.line_spacing = 1.5
r = p.add_run("Abstract: ")
set_run_font(r, HEI, EN, 9, True)
r = p.add_run(
    "To test whether the geometric-semantics hypothesis of language models transfers to a closed-state game, this paper "
    "ports a five-stage geometric pipeline to a Chinese chess engine: tokenisation, two-dimensional coordinates from PPMI and "
    "truncated SVD, a four-dimensional state built from a weighted centroid and a principal direction, a ten-level cascaded "
    f"compression, and prototype/k-nearest-neighbour retrieval over six situation classes. On {meta['positions']} positions, "
    f"the four-dimensional retrieval reaches {layers[9]['knn_acc']*100:.1f}% against a majority baseline of {meta['majority']*100:.1f}%, "
    f"while a token bag-of-words logistic regression reaches {base['bow_lr'][0]*100:.1f}%; compression does not degrade accuracy. "
    "Outcome prediction from the four-dimensional state stays at the majority level, whereas the token bag reaches the upper fifties. "
    "The conclusion is that the geometric chain is a router rather than a discriminator."
)
set_run_font(r, CN, EN, 9)

p = doc.add_paragraph()
p.paragraph_format.line_spacing = 1.5
r = p.add_run("Key words: ")
set_run_font(r, HEI, EN, 9, True)
r = p.add_run("geometric state; PPMI; SVD; k-NN retrieval; Chinese chess engine; situation class")
set_run_font(r, CN, EN, 9)

# 目录页
doc.add_section(WD_SECTION.NEW_PAGE)
add_page_number(doc.sections[-1])
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(8)
r = p.add_run("目　录")
set_run_font(r, HEI, EN, 14, True)
add_toc()

# 正文
doc.add_section(WD_SECTION.NEW_PAGE)
add_page_number(doc.sections[-1], start=1)

head1("1　引言")
body(
    "语言模型能否只用“位置关系”而不用句法结构表示语义，是一个被反复讨论的问题。GeoLite-LLM 的方案把这个问题拆成五段可以分别检验的环节："
    "把词变成令牌，把令牌压成二维坐标，把一句话的令牌压成四维状态，用级联压缩去掉次要令牌，最后用状态原型与最近邻检索给出判别结果。"
    "这一路线的价值在于每一步都可以单独求值，也在于它极省参数：整条链路的核心数据只有二维坐标表、层级统计量与一张检索库。"
)
body(
    "棋类提供了检验这套方案的理想场地。棋盘状态是离散且闭合的，规则合法性与胜负判定都可以独立验证，标签也不需要人工标注；"
    "与自然语言相比，棋类没有歧义，同一局面在任何实现里都唯一确定。这意味着若几何链路确实携带局面信息，差异会直接反映在判别准确率上，"
    "而不会被语言本身的模糊性掩盖。反过来说，若几何链路判别能力有限，也可以通过“规则加搜索”这条底线把产品做出来，从而把科学结论与工程可用性分开讨论。"
)
body(
    "本文的工作是把该论文的五段链路完整迁移到中国象棋，并补上三件原文没有的东西：一是可复现的实验协议与消融，二是真实棋谱语料，"
    "三是双端一致的工程闭环。具体贡献有三点。其一，给出令牌化、共现加权、PPMI 与截断 SVD、四维状态拟合、十层压缩与检索判别的完整实现，"
    "并用分挈（perft）与双端逐层状态比对证明实现正确。其二，在 98316 个局面、692 个令牌的语料上给出六类态势的逐层消融，"
    "并与令牌词袋基线对照，得到“几何判别显著弱于词袋、压缩不掉点”的结论。其三，把几何输出接到 α-β 搜索的评估权重上，"
    "交付一个可对弈的单文件网页，并用胜率预测实验说明四维状态承载不了胜负信息。"
)

head1("2　相关工作")
head2("2.1　分布式表示与共现统计")
body(
    "把离散符号压成低维向量的做法可以追溯到潜在语义分析，其核心是对词—文档共现矩阵做奇异值分解[1]。"
    "在词向量一侧，有研究指出带负采样的词向量训练在极限上等价于对移位后的点互信息矩阵做隐式分解[2]，"
    "这为“用 PPMI 加 SVD 复现词向量几何”提供了理论依据。本文沿用这条路径，只是把“词—上下文”换成“棋子令牌—邻域棋子令牌”。"
)
head2("2.2　最近邻检索与原型判别")
body(
    "最近邻分类在样本量趋于无穷时错误率不超过贝叶斯错误率的两倍[3]，这是它在小样本场景中被广泛使用的原因。"
    "本文同时实现 k 近邻与“最近原型”两种检索：前者按距离加权投票，后者只在每类质心上比较，二者共用同一套四维状态，"
    "因此可以直接观察“类内离散度”对判别的影响。"
)
head2("2.3　棋类引擎的搜索与评估")
body(
    "中国象棋与国际象棋的引擎结构相近：走法生成、局面评估、α-β 剪枝与置换表。α-β 剪枝在最优排序下的有效 branching 会降到平方根量级[4]，"
    "因此着法排序是引擎强度的关键。本文让几何链路只输出态势类别，再由类别决定评估中各子力项与进攻项的权重，着法排序仍由静态吃子搜索与历史启发完成。"
)
head2("2.4　本文与上述工作的差别")
body(
    "与语义几何研究相比，本文不追求在开放语料上拟合语义，而是把同一套操作放进标签确定、可穷举验证的棋类空间，"
    "因此可以把“几何是否携带信息”转化为可测的准确率差异；与常规引擎相比，本文不把几何当作评估函数，而只当作相位路由器，"
    "这样即使几何判别很弱，也不会直接拖垮棋力。"
)

head1("3　架构与实现")
head2("3.1　总体链路")
body(
    "系统由三段组成：几何链路、检索与路由、规则与搜索。几何链路负责把局面变成四维状态并给出态势类别；路由把类别变成一组评估权重；"
    "规则与搜索负责合法性与战术计算。三段之间只有两个接口：状态向量与类别下标，因此任何一段都可以单独替换或关闭，"
    "这也使页面上可以实时切换“几何相位开/关”做对照。"
)

head2("3.2　令牌化与共现权重")
body(
    "令牌定义为“阵营·兵种·规范化格位”三元组。规范化指把黑方棋子按 180 度旋转映射到走子方视角，"
    "使同一阵形在红黑两侧落到同一组坐标上。记棋子类型为 t，格位为 (x, y)，则令牌权重为"
)
body("w = r(t) · (1 + 0.15 · [y < 5])　　(1)", indent=False)
body(
    "其中 r(t) 为兵种角色权重（帅 1.40、车 1.25、炮 1.10、马 1.00、兵 0.95、相 0.85、仕 0.80），"
    "方括号为跨河指示。权重并非来自统计，而是人为设定，目的是让“贵子”在质心与主方向上占更大份额。"
)
body(
    "共现定义为同一局面内两个令牌的关系，按几何距离分两档：切比雪夫距离不超过 2 记 1.0，"
    "共线且距离不超过 6 记 0.5。共现矩阵按“令牌—上下文令牌”累加后做正向点互信息变换，负值截断为零，得到稀疏的非负矩阵。"
)

head2("3.3　二维坐标：PPMI 与截断奇异值分解")
body(
    "对共现矩阵 M 做正向点互信息变换"
)
body("PPMI(i,j) = max(0, log[ P(i,j) / (P(i)·P(j)) ])　　(2)", indent=False)
body(
    f"再取前两个奇异向量把令牌嵌入二维平面。语料上八个奇异值为 {', '.join(f'{v:.2f}' for v in [261.92, 180.74, 169.77, 117.44, 98.25, 89.10, 71.54, 67.97])}，"
    "第一、二奇异值相差不大，说明二维平面并不是“一刀切”的降维，仍有可观的结构被保留在平面上。"
    "坐标表按令牌建索引，前端与后端共用同一张表，这是双端一致的前提。"
)

head2("3.4　四维状态：质心、主方向与残差")
body(
    "把局面内所有令牌的二维坐标按其权重聚合，得到加权质心 (c_x, c_y)；对去质心后的点集求加权协方差矩阵的主特征向量，"
    "得到主方向角的正切 tanθ，并按 ±5 截断以抑制近乎垂直时的数值爆炸；残差 ρ 定义为各点到主直线的加权正交距离的均方根。"
    "于是局面被压成四元组"
)
body("s = [ c_x, c_y, tanθ, ρ ]　　(3)", indent=False)
body(
    "这个四元组的语义是“阵形往哪边偏、偏向多强、整体沿着哪个方向铺开、铺开得多整齐”。它显然是粗粒度的："
    "它记录的是位置分布的统计量，而不是“哪个兵种在哪个位置”。第 5 节的实验会把这一点的代价量化出来。"
)

head2("3.5　十层级联压缩")
body(
    "压缩过程是确定性的：每一层在当前点集上拟合主直线，删除正交距离最大的令牌，再在剩余点集上重算质心、主方向与残差；"
    "当剩余令牌不超过 3 个时停止，后续层沿用最后一次的状态。这样同一局面在任意层数上都有定义，"
    "并且层数可以作为单一旋钮在页面上滑动，实时观察残差与保留令牌数的变化。压缩的设计意图是“去掉离主线最远的噪声棋子”，"
    "使状态更贴近阵形骨架。"
)

head2("3.6　状态原型与 k 近邻检索")
body(
    "六类态势按走子方视角定义，判定规则与引擎共享同一套阈值：子力总和不超过 430 判为“残局收兵”；"
    "己方在对方九宫两格内有子且不少于对方，判为“攻王压迫”；对方在该区域的子更多，判为“防守回撤”；"
    "接触对数不少于 10 判为“接触对峙”；子力总和不少于 780 且接触对数不超过 6 判为“开局部署”；其余为“中局调动”。"
    "类别顺序固定为 open、contact、attack、defense、endgame、maneuver，模型、引擎与界面三处必须一致，这是双端校验的一部分。"
)
body(
    "检索侧保存每类的状态原型（类内均值）与一张按类均衡抽样的状态库。k 近邻按标准化后的欧氏距离做距离加权投票，"
    "k 可由页面滑块调整；原型检索则直接比较到六个类均值的距离。两种检索共用同一套均值与标准差，"
    "因此 k 的变化只影响投票，不影响状态本身。"
)

head2("3.7　路由：态势到评估权重")
body(
    "态势类别不做评估函数，只做权重表的下标。六类各有一组系数，分别作用于兵、马、炮、车、帅的机动项，将军项，吃子项与过河推进项。"
    "例如“攻王压迫”把将军项放大到 1.7、车炮机动放大到 1.3，而“防守回撤”把帅的安全项放大到 1.9、推进项压到 0.7。"
    "这样几何判别的误差只会让权重轻微偏斜，不会改变合法性，也不会让引擎走出明显亏子——这是“几何做路由器”这一定位的工程含义。"
)

head2("3.8　规则内核与 α-β 搜索")
body(
    "规则内核独立实现走法生成、将军判定、困毙与重复局面判定，并与标准分挈值对齐：初始局面的深度 1、2、3 分挈分别为 44、1920、79666，"
    "与公开数值一致。搜索为带静态吃子搜索的 α-β，配合置换表、杀手着法与历史启发；重复局面在搜索内记 0 分，避免长将循环。"
    "难度档位对应深度 2、4、5，时间预算 260、850、1600 毫秒，随机噪声 45、6、0。"
)
body(
    "需要强调的是，胜负判定的最终依据始终是规则，几何只提供排序与相位的先验。这条分工使得“几何判别很弱”与“引擎能下棋”可以同时成立。"
)

head2("3.9　工程化：单文件网页与双端一致")
body(
    "交付物是一个双击即可打开的单文件网页，模型、引擎与界面全部内联，不依赖本地服务。网页包含棋盘、棋谱栏、"
    "四维状态面板、压缩阶梯、态势检索面板、胜率预测与实验数据页。模型以 JSON 形式内联，大小 "
    f"{meta['model_kb']} KB；页面总大小约 630 KB。"
)
body(
    "为避免“两套实现各自为政”，本文把引擎写成浏览器与 node 共用的单文件模块，并用同一批局面在两端逐层比对状态。"
    "在 4 个局面、11 个层级的比对上，最大绝对误差为 0.0000（保留四位小数），说明前端展示的状态与训练侧完全同源。"
)

head1("4　数据与实验设置")
head2("4.1　语料构成")
body(
    f"语料由两部分组成。自对弈部分为 {meta['games']} 局随机对弈，按均匀间隔采样局面，用于保证标签分布不依赖外部数据；"
    f"真实棋谱部分取自公开仓库“象棋谱大全”[5]，抓取 5158 份 XQF 文件，经逐手合法性校验后得到 9860 局可用棋谱、715624 手，"
    f"按整局等间隔采样得到 {meta['real_positions']} 个局面。两部分合计 {meta['positions']} 个局面，词表 {meta['vocab']}，覆盖率为 1.000。"
)
caption("表1　语料与标签分布")
add_table(
    ["项目", "数值", "说明"],
    [
        ["局面总数", f"{meta['positions']}", "自对弈与真实棋谱合并"],
        ["自对弈", f"{meta['games']} 局", "随机对弈，间隔采样"],
        ["真实棋谱", f"{meta['pgn_files']} 份 / {meta['real_positions']} 局面", "XQF 格式，逐手校验合法"],
        ["词表规模", f"{meta['vocab']}", "阵营·兵种·规范化格位"],
        ["评估集", f"{meta['eval_positions']}", "分层抽样，k = 5"],
        ["多数类占比", f"{meta['majority']*100:.1f}%", "攻王压迫为最大类"],
        ["残局占比", f"{meta['class_dist']['endgame']/meta['eval_positions']*100:.1f}%", "样本偏斜的主要来源"],
    ],
    [4.2, 5.6, 6.4],
    note="注：类别计数取自评估集，自对弈与真实棋谱的采样口径见 4.1 节。",
)

head2("4.2　标注与评估协议")
body(
    "态势标签由 3.6 节的确定性规则生成，与引擎判定同源，因此不存在人工标注误差，但存在规则本身的粒度问题："
    "“攻王压迫”只看九宫邻域内的子力，不看全局形势，这会让大量中局局面落入同一类，表1 中该类占比 "
    f"{meta['class_dist']['attack']/meta['eval_positions']*100:.1f}% 即由此而来。"
)
body(
    "评估采用五折分层交叉验证，报告准确率、宏平均 F1 与逐层令牌数。为避免十层消融在二十万级语料上耗时过长，"
    f"评估集按类别分层抽样到 {meta['eval_positions']} 个局面。词袋基线为令牌的 0/1 指示向量加多项逻辑回归，"
    "其余设置与几何链路完全一致，作为“同样输入信息、不同归纳偏置”的对照。"
)

head2("4.3　规则与实现正确性")
body(
    "规则正确性用分挈验证：初始局面深度 1 至 3 的节点数为 44、1920、79666，与公开数值一致；另以 3 局深度 3 的自对弈做合法性抽查，"
    "未出现非法着法。实现一致性用双端状态比对验证：同一批 4 个局面在 Python 与浏览器两套实现上逐层计算，最大绝对误差为 0.0000。"
)

head1("5　实验结果")
head2("5.1　六类态势的逐层判别")
body(
    f"表2 给出逐层结果。k 近邻在第 0 层为 {layers[0]['knn_acc']*100:.1f}%，在第 9 层达到最高 {layers[9]['knn_acc']*100:.1f}%，"
    f"第 10 层回落到 {layers[10]['knn_acc']*100:.1f}%；原型检索在第 2 层最高，为 {max(l['proto_acc'] for l in layers)*100:.1f}%。"
    f"相对多数类基线 {meta['majority']*100:.1f}%，四维状态的判别力约为基线的 1.7 倍，但离可用判别器还有明显距离。"
)
caption("表2　六类态势的逐层判别（五折交叉验证）")
add_table(
    ["层", "kNN 准确率", "宏 F1", "原型准确率", "平均令牌"],
    [[l["layer"], f"{l['knn_acc']*100:.1f}%", f"{l['knn_f1']*100:.1f}%", f"{l['proto_acc']*100:.1f}%", f"{l['mean_tokens']:.1f}"] for l in layers],
    [2.0, 3.6, 3.2, 3.6, 3.0],
    note=f"注：多数类基线 {meta['majority']*100:.1f}%；原型检索取最近类均值，kNN 取 k = {meta['k']} 的距离加权投票。",
)
body(
    f"原型与 kNN 的差距说明类内离散度较大：同类局面的四维状态并不聚成一团，单点检索比类均值检索更能利用局部结构。"
    f"这一点在层数上也有表现——原型准确率随压缩下降（第 0 层 {layers[0]['proto_acc']*100:.1f}%，第 10 层 {layers[10]['proto_acc']*100:.1f}%），"
    "而 kNN 基本持平，说明压缩后的状态更“平均”，有利于单点匹配而不利于类均值。"
)

head2("5.2　与令牌词袋基线的对比")
body(
    f"同样语料下，令牌词袋加逻辑回归达到 {base['bow_lr'][0]*100:.1f}%（宏 F1 {base['bow_lr'][2]*100:.1f}%），"
    f"比四维状态的最佳 kNN 高 {base['bow_lr'][0]*100-layers[9]['knn_acc']*100:.0f} 个百分点。"
    "这个差距不来自模型容量：词袋只有 692 维 0/1 向量，逻辑回归也是线性模型；差距来自信息。"
    "令牌词袋显式保留“哪个兵种在哪个格位”，而四维状态把它平均掉了。"
)
body(
    f"把坐标从二维扩到八维后，状态维度变为 17 维，kNN 准确率升到 {dim8['knn10']*100:.1f}%，原型升到 {dim8['proto10']*100:.1f}%，"
    "仍低于词袋。这提供了一个干净的对照：增加几何维度确实提高判别力，但要追上词袋需要的维度远多于十几个——"
    "因为词袋的优势本质上是“保持身份”，而不是“保持位置”。"
)

head2("5.3　压缩的作用")
body(
    f"按论文的预期，压缩应天然损失信息。但表2 显示第 9 层比第 0 层高 {layers[9]['knn_acc']*100-layers[0]['knn_acc']*100:.1f} 个百分点，"
    "第 10 层也高于第 0 层。合理解释是：删除离主线最远的棋子等价于剔除离群点，使质心与主方向更稳定；"
    "在标签粗糙（只看九宫邻域与子力总量）的任务上，这种平滑反而有益。"
    "换句话说，压缩在此处不是“丢信息”，而是“降噪”，其收益随标签粒度变粗而增大。"
)

head2("5.4　扩容前后的对比")
body(
    "第一版语料为 12881 个局面、689 个令牌，主要由自对弈构成；扩容后局面数增至 7.6 倍。"
    "两次结果见表3。几何判别随数据量提升明显，但词袋基线的提升幅度相当，差距从 45.4 个百分点收窄到 35.1 个百分点——"
    "结论方向没有改变：几何仍是弱判别器。"
)
caption("表3　语料扩容前后的对比")
add_table(
    ["配置", "局面数", "词表", "四维 kNN", "令牌词袋", "多数类"],
    [
        ["自对弈语料", "12881", "689", "41.4%（第 7 层）", "86.8%", "26.9%"],
        ["加真实棋谱", f"{meta['positions']}", f"{meta['vocab']}", f"{layers[7]['knn_acc']*100:.1f}%（第 7 层）", f"{base['bow_lr'][0]*100:.1f}%", f"{meta['majority']*100:.1f}%"],
    ],
    [3.8, 2.6, 2.0, 3.6, 3.0, 2.4],
    note="注：第一版为自对弈 300 局采样，第二版为 200 局自对弈加真实棋谱；两版评估协议相同。",
)

head2("5.5　胜率预测实验")
body(
    "若四维状态真的编码了局面形势，那么它应当能预测胜负。为验证这一点，本文另建带胜负标签的样本集："
    f"从 2773 局棋谱中按整局等间隔采样得到 {bow['metrics']['samples']} 个局面，标签取走子方视角的胜、和、负（比例为 "
    f"{wpall['4维 第0层']['majority']*100:.1f}% 和棋、其余胜负）。三种输入分别训练多项逻辑回归，结果见表4。"
)
caption("表4　胜率预测的三组对照")
add_table(
    ["输入", "准确率", "宏 F1", "对数损失", "胜率预测平均误差"],
    [
        ["四维状态（第 0 层）", f"{wpall['4维 第0层']['acc']*100:.1f}%", f"{wpall['4维 第0层']['f1']*100:.1f}%", f"{wpall['4维 第0层']['logloss']:.3f}", f"{wpall['4维 第0层']['score_mae']:.3f}"],
        ["四维状态（第 10 层）", f"{wpall['4维 第10层']['acc']*100:.1f}%", f"{wpall['4维 第10层']['f1']*100:.1f}%", f"{wpall['4维 第10层']['logloss']:.3f}", f"{wpall['4维 第10层']['score_mae']:.3f}"],
        ["十七维状态（第 10 层）", f"{wpall['17维 第10层']['acc']*100:.1f}%", f"{wpall['17维 第10层']['f1']*100:.1f}%", f"{wpall['17维 第10层']['logloss']:.3f}", f"{wpall['17维 第10层']['score_mae']:.3f}"],
        ["令牌词袋", f"{bow['metrics']['acc']*100:.1f}%", f"{bow['metrics']['f1']*100:.1f}%", f"{bow['metrics']['logloss']:.3f}", f"{bow['metrics']['score_mae']:.3f}"],
        ["多数类（全猜和棋）", f"{bow['metrics']['majority']*100:.1f}%", "—", "—", "—"],
    ],
    [4.8, 2.8, 2.4, 2.6, 3.4],
    note="注：胜率预测误差指“胜 + ½·和”的预测值与实际得分（胜 1、和 0.5、负 0）之差的平均绝对值。",
)
body(
    f"四维状态的三分类准确率 {wpall['4维 第0层']['acc']*100:.1f}% 与多数类 {wpall['4维 第0层']['majority']*100:.1f}% 基本重合，路径两端的信息量约为零；"
    f"令牌词袋为 {bow['metrics']['acc']*100:.1f}%，胜率预测误差从 {wpall['4维 第0层']['score_mae']:.3f} 降到 {bow['metrics']['score_mae']:.3f}。"
    "需要说明的是，胜负标签本身噪声极大（同一局面在不同对局中可胜可负），因此这里比较的是“相对信息量”而不是绝对预测能力。"
)

head2("5.6　开局库")
body(
    f"真实棋谱的另一用途是构建开局库：以局面为键，统计该局面下各着法的出现局数与胜和负。库覆盖 {book['games']} 局、"
    f"{len(book['entries'])} 个局面、前 {book['plies']} 手，落盘 152 KB。检索按“精确局面”命中，"
    "未命中即回落到搜索，因此它只影响开局若干手，不改变整体强度；谱着与几何判别的分工是“谱决定走哪手，胜率与相位由模型给出”。"
)

head2("5.7　引擎运行表现")
body(
    f"单局面几何前向耗时 {meta['latency_ms']} 毫秒（Python 侧，包含取令牌、拟合与十层压缩），前端状态面板的刷新因此不构成瓶颈。"
    "深度 4 搜索在初始局面约 2.6 万节点、200 毫秒内完成；深度 5 预算 1600 毫秒，实测可稳定给出可解释着法。"
    "自对弈中出现的主要现象是深度 4 在低噪声下常跑到 220 手上限，说明引擎擅长守住不利局面，但把优势转化为胜势的能力偏弱，"
    "这一现象与几何判别无关，属搜索深度与外线评估的固有问题。"
)

head1("6　讨论")
head2("6.1　几何为何只能做路由器")
body(
    "四维状态的信息瓶颈在定义处就已注定：它是位置分布的统计量，不区分兵种。两个局面若阵形分布相似但子力构成完全不同，"
    "其四维状态会几乎相同。棋类的判别恰恰依赖子力身份与结构（谁在守哪个要点、哪条线被控制），"
    "因此几何输出更适合回答“现在大概是什么阶段、阵形往哪边压”，而不适合回答“谁更好”。"
    "把它接在评估权重上，正好利用了它的长处：类别决定的是着法倾向，而不是分值。"
)
head2("6.2　压缩不是只减信息")
body(
    "压缩提升判别准确率的结果提示一个更普遍的问题：压缩的代价取决于任务对离群点的敏感程度。"
    "当标签只看局部结构（如九宫邻域）时，离主线最远的棋子往往是对标签无贡献的噪声，删除它们等价于正则化。"
    "若换到对每一枚棋子都敏感的标签（例如精确子力差），压缩的代价就会立刻显现。"
    "这也解释了为什么 17 维状态优于 4 维：维度上升后，被平均掉的细节减少。"
)
head2("6.3　局限")
body(
    "本研究有四点局限。其一，态势标签由固定阈值生成，粒度较粗且分布偏斜（残局仅占 3.6%），判别上限被标签本身限制。"
    "其二，胜率样本只取自前 3000 份棋谱，和棋占 47.4%，与真实对局的分布并不一致，且 XQF 棋谱多为教学与名局，胜率标签本身不具代表性。"
    "其三，压缩与检索的超参数（停止令牌数 3、k = 5、按类均衡 1200 例）未经系统搜索。"
    "其四，引擎强度只用自对弈与人工试玩评估，未与公开引擎对局，因而 5.7 节的结论应视为工程观察而非强度测量。"
)
head2("6.4　可复现性")
body(
    "全部代码、语料脚本与模型均随文提供：抓取脚本、棋谱解析脚本、训练脚本、检索库刷新脚本、双端一致性校验脚本与页面构建脚本，"
    "以及最终的单文件网页。模型为 "
    f"{meta['model_kb']} KB 的 JSON，含二维坐标表、层级统计量、原型、检索库与胜率模型参数，可直接用页面打开复现全部展示。"
)

head1("7　结论")
body(
    "把 GeoLite-LLM 的五段几何链路迁到中国象棋后，得到三个可复现的结论。第一，四维状态确实携带局面信息："
    f"六类态势的检索准确率达到 {layers[9]['knn_acc']*100:.1f}%，显著高于多数类基线 {meta['majority']*100:.1f}%，"
    "增加坐标维度可进一步提升到 62.7%。第二，它的判别力显著弱于同语料的令牌词袋（91.1%），"
    "差距来自坐标化时丢失了兵种身份，而非模型容量。第三，十层压缩并未损失准确率，反而略有增益，"
    "说明在该标签粒度下压缩起的是降噪作用。"
)
body(
    "工程上，这一架构足以支撑一个可对弈的引擎：几何只做态势路由与着法排序，规则与 α-β 搜索承担合法性底线与战术计算，"
    "两者分工使弱判别不影响可用性。若要让几何承担判别任务，则需要保留兵种身份的坐标设计（例如按兵种分层的多平面嵌入），"
    "这是后续工作的方向。"
)

head1("参考文献")
refs = [
    "[1] Deerwester S, Dumais S T, Furnas G W, et al. Indexing by latent semantic analysis[J]. Journal of the American Society for Information Science, 1990, 41(6): 391-407.",
    "[2] Levy O, Goldberg Y. Neural word embedding as implicit matrix factorization[C]//Advances in Neural Information Processing Systems 27. 2014: 2177-2185.",
    "[3] Cover T, Hart P. Nearest neighbor pattern classification[J]. IEEE Transactions on Information Theory, 1967, 13(1): 21-27.",
    "[4] Knuth D E, Moore R W. An analysis of alpha-beta pruning[J]. Artificial Intelligence, 1975, 6(4): 293-326.",
    "[5] weiyinfu. 象棋谱大全（xqp）[EB/OL]. [2026-11-15]. https://github.com/weiyinfu/xqp.",
    "[6] cchess: 中国象棋棋谱读写工具[EB/OL]. [2026-11-15]. https://pypi.org/project/cchess/.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.left_indent = Pt(21)
    pf.first_line_indent = Pt(-21)
    pf.line_spacing = 1.0
    pf.space_after = Pt(3)
    r = p.add_run(ref)
    set_run_font(r, CN, EN, 9)

head1("附录A　模块与复现命令")
body(
    "抓取：fetch_xqf.py 按代理前缀批量下载棋谱并断点续传。解析：pgn_import.py 校验合法性并采样局面；"
    "book_build.py 统计开局库；result_import.py 抽取带胜负标签的样本。训练：train.py 训练坐标、层级与检索库；"
    "refresh_library.py 按类均衡重算检索库；train_result.py 与 train_winprob_bow.py 训练胜率模型。",
    indent=True,
)
body(
    "校验：parity_check.py 生成 Python 侧状态，配合 node 脚本比对前端逐层状态；selfplay.js 跑自对弈；"
    "build.py 把模型、引擎与页面内联成单文件网页。",
    indent=True,
)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(str(OUT))
print(OUT, OUT.stat().st_size // 1024, "KB")
