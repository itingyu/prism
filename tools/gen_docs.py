"""从命令注册表生成 docs/commands.md

手写的命令参考一定会烂在仓里: 上一版 README 里 `prism dzjy` / `prism jgdy` /
`prism commands` 这些命令早就不存在了, 但没人会发现 —— 文档不报错, 只有读到
的人踩坑。所以这份参考从 click 真实注册的命令对象生成, 选项说明也从那里取。

用法:
    python tools/gen_docs.py            # 写 docs/commands.md
    python tools/gen_docs.py --check    # 只比对, 过期则退出码 1 (给测试用)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from typer.main import get_command                       # noqa: E402

from prism.cli import app as app_mod                     # noqa: E402
from prism.cli.helptext import (_COMMON_ORDER, _COMMON_TAG,  # noqa: E402
                                _default_note, _flag_names, _metavar)
from prism.cli.stock import COMMANDS                     # noqa: E402

OUT = ROOT / 'docs' / 'commands.md'


def _kinds(name):
    from prism.stock.bridge.ak_families import FAM
    from prism.stock.command._schema import kind_list
    if name not in FAM:
        return 0
    return kind_list(name, FAM).get('kinds_count') or 0


def _params(cmd):
    """(位置参数, 自有选项) —— 通用选项在文首统一说明"""
    args, own = [], []
    for p in cmd.params:
        if getattr(p, 'name', '') in ('help', 'install_completion',
                                      'show_completion'):
            continue
        if not hasattr(p, 'is_flag'):
            args.append(p)
        elif p.name not in _COMMON_ORDER:
            own.append(p)
    return args, own


def _usage(name, args):
    pos = ''
    for a in args:
        pos += f' [{a.name}]' if not a.required else f' <{a.name}>'
    return f'prism {name}{pos} [选项]'


def _line(name, summary, usage, n_kinds):
    out = [f'### `{name}`' + (f' · {summary}' if summary else ''), '']
    tail = f' · 口径 {n_kinds} 个（`prism {name} --list`）' if n_kinds else ''
    out.append(f'`{usage}`{tail}')
    return out


def render():
    cli = get_command(app_mod.app)
    panels = app_mod._PANELS
    assigned = {n for names in panels.values() for n in names}
    rest = sorted(n for n in COMMANDS if n not in assigned)

    n_kinds = sum(_kinds(c) for c in COMMANDS)
    lines = [
        '# 命令参考',
        '',
        '> 本文件由 `python tools/gen_docs.py` 从命令注册表生成，**不要手改**。',
        '> 改了命令就跑一次生成，`tests/test_docs.py` 会拦住过期版本。',
        '',
        f'共 {len(COMMANDS)} 个命令；其中 {len(_kinds_cmds())} 个带扩展口径，'
        f'合计 {n_kinds} 个口径。',
        '',
        '## 通用选项',
        '',
        '每条命令都可用的选项（各自命令的 `-h` 里也有）：',
        '',
        '| 选项 | 含义 |',
        '| --- | --- |',
        '| `-f/--format` | 输出格式：`text`（默认）/ `markdown` / `json` |',
        '| `-o/--output` | 写入文件；给目录则按时间命名；`-o -` 仍是标准输出 |',
        '| `--kind <口径>` | 走该命令的扩展口径（先 `--list` 看清单） |',
        '| `--list` | 列出该命令的扩展口径 |',
        '| `--source <方法名>` | 点名数据源层方法（仅部分命令，见 [数据源](sources.md)） |',
        '| `--arg k=v` | 给底层接口额外传参，可重复 |',
        '| `-n/--limit <N>` | 条数（仅部分命令） |',
        '',
        'JSON 输出统一信封与退出码见 [输出格式](output.md)。',
        '',
    ]

    groups = list(panels.items()) + ([('其他', rest)] if rest else [])
    for panel, names in groups:
        names = [n for n in names if n in COMMANDS]
        if not names:
            continue
        lines += [f'## {panel}', '']
        for name in names:
            fn = COMMANDS[name]
            doc = (fn.__doc__ or '').strip().splitlines()
            summary = doc[0].strip() if doc else ''
            cmd = cli.commands.get(name)
            args, own = _params(cmd) if cmd is not None else ([], [])
            lines += _line(name, summary, _usage(name, args), _kinds(name))
            for p in args:
                lines.append(f'- `<{p.name}>` {(p.help or "").strip()}')
            if own:
                lines.append('')
                for p in own:
                    meta = '' if p.is_flag else f' <{_metavar(p)}>'
                    help_ = (p.help or '').strip() + _default_note(p)
                    lines.append(f'- `{_flag_names(p)}{meta}` {help_}'.rstrip())
            lines.append('')
    lines += _extra()
    return '\n'.join(lines).rstrip() + '\n'


def _kinds_cmds():
    return [c for c in COMMANDS if _kinds(c)]


def _extra():
    """非股票命令 (position / config / pydata) 单列一节, 它们不在 COMMANDS 表"""
    from typer.main import get_command

    from prism.cli.app import app

    cli = get_command(app)
    out = ['## 其他命令', '']
    for name in ('position', 'config', 'pydata'):
        node = cli.commands.get(name)
        if node is None:
            continue
        doc = (node.help or '').strip().splitlines()
        out.append(f'### `{name}`' + (f' · {doc[0].strip()}' if doc else ''))
        out.append('')
        if hasattr(node, 'commands'):
            for sub in sorted(node.commands):
                d = (node.commands[sub].help or '').strip().splitlines()
                out.append(f'- `prism {name} {sub}` — {d[0].strip() if d else ""}')
        else:
            out.append(f'用法见 `prism {name} -h`。')
        out.append('')
    return out


def main():
    text = render()
    if '--check' in sys.argv:
        old = OUT.read_text(encoding='utf-8') if OUT.exists() else ''
        if old != text:
            print(f'{OUT} 已过期，跑 python tools/gen_docs.py 重新生成')
            return 1
        print('docs/commands.md 是最新的')
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding='utf-8')
    print(f'已写入 {OUT} ({len(text.splitlines())} 行)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
