# -*- coding: utf-8 -*-
"""把 model_triple.json 里的三空间坐标 + 45 维 RBF 树导出成 C++ 头文件 geo45.h。

只导 C++ 侧真正要用的部分：
  - coords3a/3b/3c：令牌 key（S/O + 兵种 + 归一化坐标）→ 3 维坐标
  - tree.model：mean/std/centers/local(w,b)/glob(w,b)/h/lam/hScale
不导 book / battle / traps / blacklist —— 那些由搜索层与 C++ 侧的其它模块负责。
"""
import json

KEY_ORDER = ['S', 'O']
DIM = 45
STRIDE = 48   # 补齐到 4 的倍数，C++ 侧可直接四路 SIMD 累加，尾部零不影响结果


def token_index(key):
    """'S5@47' -> (role, type, by, bx) -> 扁平槽位。role: S=0, O=1。"""
    role = 0 if key[0] == 'S' else 1
    t = int(key[1])
    bx = int(key[3])
    by = int(key[4])
    return (role * 7 + (t - 1)) * 90 + by * 9 + bx


def main():
    m = json.load(open('model_triple.json', encoding='utf-8'))
    tabs = [m['coords3a'], m['coords3b'], m['coords3c']]

    # 槽位表：1260 个 (role,type,bx,by) 组合里只有实际用到的那些有坐标
    slot = [-1] * 1260
    vecs = []
    for k in sorted(tabs[0].keys()):
        if not all(k in tb for tb in tabs):
            continue
        slot[token_index(k)] = len(vecs)
        vecs.append([tabs[i][k] for i in range(3)])

    t = m['tree']['model']
    K = len(t['centers'])
    def pad(row):
        row = [float(x) for x in row]
        return row + [0.0] * (STRIDE - len(row))

    mean = pad(t['mean'])
    std = pad(t['std'])
    lw = [v for c in t['local'] for v in pad(c['w'])]
    lb = [float(c.get('b') or 0.0) for c in t['local']]
    gw = pad(t['glob']['w'])
    gb = float(t['glob'].get('b') or 0.0)
    centers = [v for c in t['centers'] for v in pad(c)]

    h = float(m['tree']['h'])
    hscale = float(m['tree'].get('hScale') or 1.0)
    lam = float(m['tree']['lam'])

    def arr(name, ctype, vals, per=8, fmt='%.6ff'):
        out = [f'static const {ctype} {name}[{len(vals)}] = {{']
        for i in range(0, len(vals), per):
            out.append('  ' + ','.join(fmt % v for v in vals[i:i + per]) + ',')
        out.append('};')
        return '\n'.join(out)

    lines = []
    lines.append('// 自动生成：export_geo45.py ← model_triple.json。请勿手改。')
    lines.append('// 45 维几何树的 C++ 侧参数：三空间坐标 + 64 专家 RBF + 局部线性。')
    lines.append('#pragma once')
    lines.append(f'static const int GEO_DIM = {DIM};')
    lines.append(f'static const int GEO_STRIDE = {STRIDE};')
    lines.append(f'static const int GEO_K = {K};')
    lines.append(f'static const int GEO_NVEC = {len(vecs)};')
    lines.append(f'static const float GEO_H = {h:.6f}f;')
    lines.append(f'static const float GEO_HSCALE = {hscale:.6f}f;')
    lines.append(f'static const float GEO_LAM = {lam:.6f}f;')
    lines.append('')

    # 槽位映射表（-1 表示该令牌没有坐标，特征计算时丢弃）
    flat_slot = []
    for i in range(0, 1260, 20):
        flat_slot.append('  ' + ','.join('%d' % v for v in slot[i:i + 20]) + ',')
    lines.append('static const short GEO_SLOT[1260] = {')
    lines.extend(flat_slot)
    lines.append('};')
    lines.append('')

    # 布局：[空间][槽位][3]，空间优先，方便 C++ 侧按空间连续取数
    xyz = [c for sp in range(3) for entry in vecs for c in entry[sp]]
    lines.append(arr('GEO_XYZ', 'float', xyz, per=9, fmt='%.7ff'))
    lines.append('')
    lines.append(arr('GEO_MEAN', 'float', mean))
    lines.append(arr('GEO_STD', 'float', std))
    lines.append(arr('GEO_CN', 'float', centers))
    lines.append(arr('GEO_LW', 'float', lw))
    lines.append(arr('GEO_LB', 'float', lb))
    lines.append(arr('GEO_GW', 'float', gw))
    lines.append(f'static const float GEO_GB = {gb:.6f}f;')
    lines.append('')

    open('geo45.h', 'w', encoding='utf-8').write('\n'.join(lines))
    import os
    print('geo45.h %.1f KB  slots=%d  K=%d  dim=%d  h=%.2f hScale=%.2f'
          % (os.path.getsize('geo45.h') / 1024, len(vecs), K, DIM, h, hscale))


if __name__ == '__main__':
    main()
