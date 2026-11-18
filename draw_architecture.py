"""绘制 GeoLite 当前价值模型架构图（离线训练 + 在线决策）。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

BG = "#F6F8FB"
INK = "#1F2937"
MUTED = "#6B7280"
TEAL = "#0F766E"
TEAL_BG = "#E6F4F1"
AMBER = "#B45309"
AMBER_BG = "#FEF3E2"
BLUE = "#1D4ED8"
BLUE_BG = "#EAF0FF"
GRAY_BORDER = "#CBD5E1"

fig, ax = plt.subplots(figsize=(16, 9), dpi=220)
fig.patch.set_facecolor(BG)
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

ax.text(4, 95.2, "GeoLite 象棋 · 神经 + 几何混合架构", fontsize=22, weight="bold",
        color=INK, ha="left", va="center")
ax.text(4, 91.5, "离线：20 万局面由皮卡鱼 movetime=50 打标 → 10×9×14 棋子平面 + 45 维几何 → 神经价值头；在线：几何给候选，神经给分，HGB 树给战术与结构先验",
        fontsize=9.5, color=MUTED, ha="left", va="center")


def box(x, y, w, h, text, border, face="white", fs=8.6, bold_first=True, lw=1.2):
    shadow = FancyBboxPatch((x + 0.28, y - 0.28), w, h,
                            boxstyle="round,pad=0.02,rounding_size=0.55",
                            linewidth=0, facecolor="#0F172A", alpha=0.07, zorder=1)
    ax.add_patch(shadow)
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.55",
                       linewidth=lw, edgecolor=border, facecolor=face, zorder=2)
    ax.add_patch(p)
    lines = text.split("\n")
    ax.text(x + 0.6, y + h - 0.75, lines[0], fontsize=fs + 0.7, color=border,
            weight="bold" if bold_first else "normal", ha="left", va="top", zorder=3)
    if len(lines) > 1:
        ax.text(x + 0.6, y + h - 2.35, "\n".join(lines[1:]), fontsize=fs,
                color=INK, ha="left", va="top", linespacing=1.45, zorder=3)


def arrow(x1, y1, x2, y2, color="#94A3B8", rad=0.0, lw=1.4):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=13, linewidth=lw, color=color,
                                 connectionstyle=f"arc3,rad={rad}", zorder=4))


def section(x, y, txt, color):
    ax.text(x, y, txt, fontsize=8.2, color=color, weight="bold", ha="left", va="center")
    ax.plot([x, x + 2.6], [y - 0.65, y - 0.65], color=color, lw=1.2, solid_capstyle="round")

# ① 数据
section(2, 87.2, "① 数据与标签（离线）", TEAL)
box(2, 73.0, 21.5, 12.6,
    "200,000 局面池\n"
    "pgn 33,162｜result 10,931\n"
    "battle 3,752｜battle_log 76,222\n"
    "selfplay 60,084｜pgn_mirror 15,849",
    TEAL, TEAL_BG)
box(2, 57.0, 21.5, 12.0,
    "皮卡鱼 movetime=50\n"
    "7 个分片，200,000 / 200,000\n"
    "side-to-move cp\n"
    "镜像：180° 旋转 + 颜色取反",
    TEAL, "white")
box(2, 41.0, 21.5, 12.0,
    "标签现实（不是 side 错位）\n"
    "mean 871.9｜median 30\n"
    "将死分 16,422｜0 分 784\n"
    "偏正来自对局样本选择偏差",
    TEAL, "white")
arrow(12.75, 73.0, 12.75, 69.2)
arrow(12.75, 57.0, 12.75, 53.2)

# ② 特征
section(26.5, 87.2, "② 几何特征", BLUE)
box(26.5, 50.0, 17.5, 25.0,
    "双输入表示\n"
    "10×9×14 棋子平面\n"
    "（1260 维，side-to-move 视角）\n\n"
    "45 维几何特征\n"
    "21 维 三空间几何\n"
    "9 维 形状/轮廓\n"
    "9 维 子力结构\n"
    "6 维 九宫/边线威胁",
    BLUE, BLUE_BG, fs=8.2)
arrow(23.5, 62.0, 26.5, 62.0, color=TEAL)

# ③ 模型
section(46.5, 87.2, "③ 神经评估 + 几何树先验", AMBER)
box(46.5, 66.0, 25.5, 17.0,
    "神经价值头（主评估）\n"
    "输入 1260 平面 + 45 几何\n"
    "MLP 1305 → 128 → 64 → 1\n"
    "留出 MAE 160.6 / R² 0.896\n"
    "固定局面 CPL 76.5\n"
    "几何作为显式输入，不丢几何",
    AMBER, AMBER_BG, fs=8.0)
box(46.5, 46.0, 25.5, 17.0,
    "HGB45 几何树（结构先验）\n"
    "600 棵 × 63 叶；MAE 192.3\n"
    "固定局面 CPL 86.3\n"
    "与神经按 10% 融合：CPL 76.3\n"
    "强制手搜索仍用 HGB 叶子\n"
    "负责战术与几何结构兜底",
    AMBER, "white", fs=8.0)
arrow(44.0, 69.0, 46.5, 73.0, color=AMBER)
arrow(44.0, 58.0, 46.5, 56.0, color=AMBER)

# 模型 → 在线评估器
arrow(72.0, 74.0, 73.0, 58.0, color=AMBER, rad=0.08)
arrow(72.0, 56.0, 73.0, 53.0, color=AMBER, rad=0.05)

# 模型选择备注
ax.text(46.5, 40.5, "默认 model_value（保留 depth1 陷阱）\n新混合模型 model_value_nn_hgb90（CPL 76.3，尚未替换默认）",
        fontsize=7.4, color=MUTED, ha="left", va="top", linespacing=1.5)

# ④ 在线
section(73.0, 87.2, "④ 在线单局决策（nnhf）", TEAL)
box(73.0, 76.0, 24.5, 8.2,
    "棋盘局面\nFEN / 90 格 / 红黑先手", TEAL, TEAL_BG, fs=8.6)
box(73.0, 63.5, 24.5, 9.5,
    "三轨候选生成\n几何引力 + 战术强制手\n+ 历史库高频着法", TEAL, "white", fs=8.4)
box(73.0, 51.0, 24.5, 9.5,
    "神经 + HGB 融合估值\n90% 神经分 + 10% 几何树\n→ cp / 候选排序", TEAL, "white", fs=8.4)
box(73.0, 39.0, 24.5, 9.0,
    "HGB 强制手搜索\n3 层吃子 / 叫将\n把连杀与交换看清", TEAL, "#FEF9E7", fs=8.4)
box(73.0, 27.0, 24.5, 9.0,
    "战术叶子硬校验\nSEE｜解将｜一步杀过滤\n终局将死优先", TEAL, "white", fs=8.4)
box(73.0, 16.0, 24.5, 7.0,
    "选步 / UCI 输出\n最优着 + 备选着", TEAL, TEAL_BG, fs=8.6)
for y1, y2 in [(76.0, 72.2), (63.5, 60.2), (51.0, 48.2), (39.0, 36.2), (27.0, 23.2)]:
    arrow(85.25, y1, 85.25, y2, color=TEAL)

# ⑤ 评测
ax.plot([2, 97], [17.3, 17.3], color="#D7DEE8", lw=1.0)
section(2, 15.8, "⑤ 同口径评测（固定局面 / 留出集）", BLUE)
metrics = [
    ("CPL 76.3", "神经+HGB90\n160 局面 / 117 有效", TEAL, TEAL_BG),
    ("MAE 160.6", "神经价值头\n30k 留出集", BLUE, BLUE_BG),
    ("0 / 20 胜", "对皮卡鱼 movetime=50\n平均 48.3 手", AMBER, AMBER_BG),
    ("1305 维", "1260 平面 + 45 几何\n完全离线、零外链", "#64748B", "#F1F5F9"),
]
for i, (big, small, c, bg) in enumerate(metrics):
    x = 2 + i * 24.0
    box(x, 5.2, 22.0, 9.6, "", c, bg)
    ax.text(x + 11.0, 11.9, big, fontsize=12.0, color=c, weight="bold", ha="center", va="center")
    ax.text(x + 11.0, 8.2, small, fontsize=7.4, color=MUTED, ha="center", va="center", linespacing=1.5)

ax.text(97.0, 2.2, "结论：神经给静态分、HGB 树给战术与结构先验；固定 CPL 从 86.3 降到 76.3，但对 movetime=50 仍 0/20、平均 48.3 手",
        fontsize=7.0, color=MUTED, ha="right", va="center")

fig.savefig(r"C:\Users\kevion\Desktop\象棋博弈\GeoLite象棋\架构图_当前模型.png",
            bbox_inches="tight", facecolor=BG)
print("saved")
