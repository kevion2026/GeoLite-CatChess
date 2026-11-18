# CatChess-v2.0

几何特征 + MLP 价值头的象棋引擎。

棋盘先投影到三张几何坐标表上变成点云，取出 45 维形状统计（三空间质心/主轴/残差、9 形、9 子力、6 威胁），
再拼上一维传统棋子平面分，送进一个 46→128→64→1 的小网络，输出走子方视角的 cp。

- 可执行文件：`CatChess-v2.0.exe`（Windows x64，静态链接，无运行库依赖）
- 接口：UCI 子集，可直接挂到 Arena / 象棋巫师 / 命令行
- 架构细节：见同目录 `CatChess-v2.0-架构.md`

## 与 v1.0pro-preview 的区别

| | v1.0pro-preview | v2.0 |
|---|---|---|
| 几何 45 维特征 | 有 | **全部保留** |
| 价值头 | 64 专家 RBF 门控 + 局部线性 | MLP 128-64（numpy 训练，AVX2 前向） |
| 平面模型 | 按 65:35 手调融合 | 作为第 46 维输入，由网络自己学配比 |
| 首选一致率（深参考） | 18.8% | **24.8–26.5%** |
| 均势局面 MAE | 86.8 | **69.8** |

换掉 RBF 的原因是它在 45 维空间里没有分辨力：到最近中心的 d² 中位数约 20，而核宽 8.75，
有效专家数是 62/64——K 从 64 加到 256，验证集误差一动不动。

## 快速开始

```bash
./CatChess-v2.0.exe

uci
position startpos
go movetime 1000
quit
```

输出示例：

```
info depth 7 score 11 nodes 90241 time 234 nps 385645
bestmove b2e2
```

把 exe 路径填进 GUI 的 UCI 引擎设置即可。没有开局库，第一步靠搜索。

## 支持的命令

| 命令 | 说明 |
|---|---|
| `uci` / `isready` / `quit` | 标准握手 |
| `ucinewgame` | 清空置换表与历史表 |
| `position startpos [moves ...]` | 着法逐条校验，非法则拒绝 |
| `position fen <FEN> [moves ...]` | FEN 需 10 行、每行 ≤9 列、双方各一将 |
| `go movetime N` | 思考 N 毫秒 |
| `go depth N` | 固定深度（上限 88） |
| `go wtime/btime/winc/binc` | 按剩余时间自动分配 |
| `go infinite` | 无 `stop` 通道，30 秒硬上限 |
| `eval` / `d` / `fen` / `perft N` | 调试：评估值、棋盘、FEN、perft |

## 文件清单

| 文件 | 作用 |
|---|---|
| `CatChess-v2.0.exe` | 引擎本体 |
| `CatChess-v2.0-架构.md` | 架构说明与实测数据 |
| `xq.cpp` | 搜索引擎：α-β + 置换表 + 空着裁剪 + 静态搜索 + UCI |
| `mlp_eval.h` | 价值头前向（AVX2） |
| `mlp46.h` | 网络权重（由 `export_mlp.py` 生成，勿手改） |
| `geo_eval.h` | 45 维几何特征（三空间 + 形 + 子力 + 威胁） |
| `geo45.h` | 三张坐标表（几何特征查表用） |
| `linear_weight_aug.h` | 1260 参数棋子平面（第 46 维输入的来源） |
| `linear_weight_static.h` | 纯平面版权重 |
| `build.sh` | 一键重建 |
| `selfcheck.sh` | 出厂自检 |

## 重建

需要 MinGW-w64 的 g++（GCC 9+，AVX2 更好）。w64devkit 这类绿色包即可。

```bash
./build.sh v2              # → CatChess-v2.0.exe（SCALE 默认 0.75）
SCALE=0.6 ./build.sh v2    # 改评估缩放（越小剪枝越狠、搜索越深）
./build.sh                 # → CatChess-v1.0pro-preview.exe（上一代，仍然可构建）
```

Windows 下如果 g++ 报 `Cannot create temporary file ... Permission denied`，
是默认临时目录不可写，`build.sh` 已把 `TMPDIR/TMP/TEMP` 指到本地 `.tmpbuild/`。

## 自检

```bash
./selfcheck.sh
```

应输出 perft 1/2/3 = 44 / 1920 / 79666，并给出一个 `bestmove`。

## 实测成绩

固定 117 个实战局面，每步 300ms。区分两种参考分——这一点很重要：

| 参考分 | 版本 | CPL | p90 | top1 |
|---|---|---|---|---|
| 皮卡鱼 60ms | v1.0pro-preview | 64.5 | 162 | 17.9% |
| 皮卡鱼 60ms | v2.0 | **58.5** | 151 | 22.2% |
| 皮卡鱼 500ms | v1.0pro-preview | **71.9** | 148 | 18.8% |
| 皮卡鱼 500ms | v2.0 | 71.0–74.7 | 170–185 | **24.8–26.5%** |

**换成深参考后 CPL 的差距消失了**：v2 的首选着法更接近真值（top1 +35%），
但非首选着法的失误更大，两者抵消。浅参考下那 9% 的改善，是在贴近浅搜的判断而非真实最优。

对局层面（vs v1.0pro-preview，随机 4 手开局、先后手交替）：
250ms 24 局得分 0.458，depth 6 30 局得分 0.517。**没有测出显著差异**——
54 局的标准误约 0.068，要分辨 30 Elo 需要 400 局以上。

## 已知限制

1. **残局是短板**。训练集里总子力 <40 的局面只占 4%，等深度自对弈 30 局里有 25 局和棋、
   平均 180 手走到上限——优势赢不下来。
2. 深度比上一代浅约 0.3 层：评估变准会让搜索树变大，这是固有取舍。
3. 左右不完全对称（MLP 是学出来的，镜像差几 cp）。
4. 没有开局库，没有增量评估，单线程阻塞搜索（不支持 `stop` / `ponderhit`）。
5. 静态搜索不解「困毙」（主搜索层正确）。

## 许可与出处

内部版本，权重与代码来自 GeoLite象棋项目。UCI 标识：
`id name CatChess-v2.0` / `id author GeoLite / CatChess`。
