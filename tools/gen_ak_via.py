"""生成 ak_via.py: 上游接口 → 有专用命令的映射

同一份上游数据有两条入口: 专用命令 (prism lhb, 字段做过筛选与单位折算)
和通用口径 (--kind, 原样透传上游字段)。用户在 --kind 里拿到裸字段时,
应该知道"这个接口有专用命令, 字段更规整"。

从 bridge/ak.py 的薄包装里抽: 每个包装函数调 rows('stock_xxx'),
那就是它对应的上游接口; 函数名对应命令层的动作名。

用法: PYTHONPATH=src python tools/gen_ak_via.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src' / 'prism' / 'stock' / 'bridge' / 'ak.py'
OUT = ROOT / 'src' / 'prism' / 'stock' / 'bridge' / 'ak_via.py'

# 薄包装名 → (CLI 命令名, 该命令要额外打开的标志)
# 薄包装按数据源语义命名, CLI 命令按用户语义命名, 两边对不上就在这里对齐
FLAGS = {
    'lhb_yyb': ('lhb', {'yyb': True}),
    'dzjy': ('block-trade', {}),
    'jgdy': ('survey', {}),
    'yanbao': ('analyst-report', {}),
    'gdhs': ('holder-count', {}),
    'unlock_summary': ('unlock', {}),
    'hsgt': ('stock-connect', {}),
    'hsgt_snapshot': ('stock-connect', {}),
    'fin_indicator': ('financials', {}),
}


def main() -> int:
    tree = ast.parse(SRC.read_text(encoding='utf-8'))
    pairs = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        func = None
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                    and sub.func.id == 'rows' and sub.args
                    and isinstance(sub.args[0], ast.Constant)
                    and isinstance(sub.args[0].value, str)):
                func = sub.args[0].value
                break
        if not func:
            continue
        cmd, flags = FLAGS.get(node.name, (node.name, {}))
        pairs.append((func, cmd, flags))
    if not pairs:
        print('没抽到映射, bridge/ak.py 结构可能变了', file=sys.stderr)
        return 1
    pairs.sort()
    # 映射到的命令必须真的存在, 否则提示是错的
    sys.path.insert(0, str(ROOT / 'src'))
    from prism.cli.stock import COMMANDS
    missing = sorted({cmd for _, cmd, _ in pairs if cmd not in COMMANDS})
    if missing:
        print(f'映射到的命令不存在: {missing}', file=sys.stderr)
        return 1
    lines = [
        '"""上游接口 → 专用命令的映射 (由 tools/gen_ak_via.py 生成, 勿手改)',
        '',
        '同一份上游数据有两条入口:',
        '  - 专用命令 (prism lhb): 字段做过筛选、单位折算、窗口取数, 结果更规整',
        '  - 通用口径 (--kind):    原样透传上游字段, 想自己加工时用',
        '',
        '这份表让 prism schema 能告诉用户"这个接口还有更规整的入口"。',
        '"""',
        '',
        '# interface → (命令名, 额外标志)',
        'INTERFACE_VIA = {',
    ]
    for func, cmd, flags in pairs:
        lines.append(f"    {func!r}: ({cmd!r}, {flags!r}),")
    lines.append('}')
    lines.append('')
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'写入 {OUT} ({len(pairs)} 条)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
