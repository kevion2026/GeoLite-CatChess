# GeoLite / CatChess

GeoLite/CatChess 是一个以几何评估为核心的 Windows 中国象棋引擎，配套一个本地网页对弈前端。棋盘被投影到几何坐标表上，提取形状、子力与威胁特征，再与棋子平面分融合；搜索层使用带置换表的迭代加深 α-β，支持 UCI 子集。

## 快速开始

需要 Node.js 18+。

```powershell
cd web
node server.js
```

浏览器打开 <http://127.0.0.1:8770/>。页面左栏「模型修改」可以切换仓库内自带的 `CatChess-*.exe`；引擎进程会重启，棋局保留。

引擎也可以直接作为 UCI 程序使用：

```text
uci
isready
position startpos
go movetime 1000
quit
```

## 目录

| 路径 | 内容 |
|---|---|
| `xq.cpp`、`geo_eval.h`、`mlp_eval.h` | C++ 搜索引擎、几何特征与价值头 |
| `web/` | 本地网页前端与 Node 服务 |
| `CatChess-*.exe` | 已编译的发布版引擎（Windows x64） |
| `model_*.json`、`*.h` | 评估模型与导出的权重 |
| `*.py`、`*.js` | 数据生成、训练、评测与实验脚本 |
| `*.md` | 架构、实验记录与测评报告 |
| `data/` | 训练数据集（未提交，体积约 2.6GB） |
| `pikafish/` | 第三方 Pikafish 资料与二进制（未提交） |

## 说明

- 引擎与网页均为本地运行，不联网。
- `server.js` 默认加载 `CatChess-V1.0-pro.exe`；可通过 `CATCHESS_EXE` 环境变量或页面上的模型按钮切换。
- 仓库保留发布 exe 与模型权重，便于直接运行；训练数据集、第三方引擎和构建中间产物由 `.gitignore` 排除。
