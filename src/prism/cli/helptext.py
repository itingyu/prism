"""grep 风格的纯文本帮助: 对齐两列, 不画框, 不换行, 只说用法

typer 默认用 rich 表格: 窄终端下说明被折成两三行, 再加边框, 85 个命令
要滚 130+ 行且难以 `grep`。这里接管 -h/--help, 直接输出机器友好/人也好
扫的文本 —— 一行一个选项, 说明不折行, 没有 `[default: x]` 之类的富文本标记。

数据源是 click 真实注册的命令对象 (不是手写清单), 所以命令改名/加参不会
让帮助失真; 只过滤掉 typer 自动加的补充项 (--install-completion 等)。
"""
import unicodedata

# 这些选项由 typer/click 自动加, 对使用者没有信息量
_HIDDEN = {'help', 'install_completion', 'show_completion'}
# 各命令签名里都有的公共选项, 单独归组, 免得每条命令的帮助都重复一大段
_COMMON = {'fmt', 'output', 'kind', 'list_kinds', 'source', 'arg', 'limit'}
# 通用项固定按这个次序显示, 不随函数签名里参数的先后漂移
_COMMON_ORDER = ['fmt', 'output', 'kind', 'list_kinds', 'source', 'arg', 'limit']
# 通用项在单条命令帮助里压成一行: 它们的含义全仓一致, 逐条展开纯属重复
_COMMON_TAG = {'fmt': 'text|markdown|json', 'output': '路径', 'kind': '口径',
               'list_kinds': '', 'source': '方法名', 'arg': 'k=v', 'limit': '条数'}

_LABEL_W = 26


def _metavar(p):
    mv = getattr(p, 'metavar', None)
    if mv:
        return mv
    t = getattr(p, 'type', None)
    name = getattr(t, 'name', '') or 'str'
    return {'text': 'str'}.get(name, name)


def _default_note(p):
    d = p.default
    if d is None or d is False or d == '' or d == () or d == []:
        return ''
    if isinstance(d, bool):
        return ''
    return f' (默认 {d})'


def _dw(s):
    """显示宽度: 中文/全角算 2 格, 否则按字算"""
    return sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in s)


def _row(names, meta, help_, width):
    label = f'{names} {meta}'.strip()
    pad = width - _dw(label)
    if pad < 1:
        # 名字太长就换到下一行挂说明, 也比整段折行好读
        return f'  {label}\n{" " * (width + 2)}{help_}'
    return f'  {label}{" " * pad} {help_}' if help_ else f'  {label}'


def _collect(cmd):
    """拆成 (位置参数, 命令自有选项, 公共选项)"""
    args, own, common = [], [], []
    for p in cmd.params:
        if getattr(p, 'name', '') in _HIDDEN:
            continue
        # typer 自带一份 click 副本 (typer._click), isinstance 认不出它自己
        # 造的对象 —— 只能按有没有 opts 区分 Option / Argument。
        if not hasattr(p, 'is_flag'):      # Argument 没有 is_flag
            args.append(p)
            continue
        (common if p.name in _COMMON else own).append(p)
    common.sort(key=lambda p: _COMMON_ORDER.index(p.name)
                if p.name in _COMMON_ORDER else len(_COMMON_ORDER))
    return args, own, common


def _flag_names(p):
    names = list(p.opts) + list(p.secondary_opts)
    names = [n for n in names if n.startswith('-')]
    names.sort(key=lambda n: (n.startswith('--'), len(n)))   # 短标志在前
    return '/'.join(names)


def _option_rows(params, width):
    rows = []
    for p in params:
        names = _flag_names(p)
        meta = '' if p.is_flag else f'<{_metavar(p)}>'
        help_ = (p.help or '').strip() + _default_note(p)
        rows.append(_row(names, meta, help_, width))
    return rows


def _common_line(params):
    """通用选项压成一行, 只留名字 + 最必要的一个词"""
    parts = []
    for p in params:
        tag = _COMMON_TAG.get(p.name, (p.help or '').split(';')[0].strip())
        note = _default_note(p) if p.name == 'limit' else ''
        parts.append(f'{_flag_names(p)}' + (f' {tag}' if tag else '') + note)
    return '  '.join(parts)


def render_cmd(cli, name, path='prism'):
    """单条命令的帮助: 用法行 + 位置 + 选项 + 公共选项"""
    cmd = cli.commands.get(name)
    if cmd is None:
        return None
    args, own, common = _collect(cmd)

    pos = ' '.join(f'[{a.name}]' if not a.required else f'<{a.name}>'
                   for a in args)
    head = f'{path} {name}'
    if pos:
        head += f' {pos}'
    head += ' [选项]'

    doc = (cmd.help or '').strip().splitlines()
    summary = doc[0].strip() if doc else ''

    out = [f'用法: {head}']
    if summary:
        out.append(f'      {summary}')

    width = _LABEL_W
    if args:
        out.append('')
        out.append('位置')
        for a in args:
            out.append(_row(f'<{a.name}>', '', (a.help or '').strip(), width))
    if own:
        out.append('')
        out.append('选项')
        out.extend(_option_rows(own, width))
    if common:
        out.append('')
        out.append('通用  ' + _common_line(common))
    return '\n'.join(out)


def render_group(grp, path):
    """命令组 (position / config): 列出子动作, 指向各自的 -h"""
    lines = [f'用法: {path} <子动作> [选项]']
    doc = (grp.help or '').strip().splitlines()
    if doc:
        lines.append(f'      {doc[0].strip()}')
    lines.append('')
    lines.append('子动作')
    width = max((_dw(n) for n in grp.commands), default=8) + 2
    for n in sorted(grp.commands):
        sub = grp.commands[n]
        first = (sub.help or '').strip().splitlines()
        lines.append(_row(n, '', first[0].strip() if first else '', width))
    lines.append('')
    lines.append(f'详情: {path} <子动作> -h')
    return '\n'.join(lines)


def _dense(panels, commands, width=78):
    """按面板密排命令名: 一行多个, 只留名字

    85 条命令逐条配一句说明要占 85 行, 而说明本来就能用 `prism <命令> -h`
    拿到 —— 顶层帮助只需要"有哪些命令、怎么分组"。
    """
    lines, seen = [], set()
    groups = list(panels.items()) + [('其他', [n for n in commands
                                              if n not in {x for v in panels.values() for x in v}])]
    for panel, names in groups:
        names = [n for n in names if n in commands]
        if not names:
            continue
        seen.update(names)
        lines.append(f'{panel} ({len(names)})')
        cur = '  '
        for n in names:
            if _dw(cur) + _dw(n) + 2 > width:
                lines.append(cur.rstrip())
                cur = '  '
            cur += n + '  '
        if cur.strip():
            lines.append(cur.rstrip())
    return '\n'.join(lines)


def render_root(usage, panels, commands):
    """顶层帮助: 用法 + 按面板密排的命令名 + 去哪查详情"""
    return (f'{usage}\n'
            f'命令目录 ({len(commands)} 个; 详情看 `prism <命令> -h`, 搜命令用 `prism lookup <词>`)\n'
            f'{_dense(panels, commands)}\n'
            f'其他  position (持仓台账)  config (配置)  pydata (外部库透传)\n'
            f'调试  -d/--debug 打开诊断日志 (-dd 连三方库)  --log-file <路径> 全量落文件')


def render(argv, panels=None):
    """按 argv 决定渲染哪一份帮助 (顶层 / position / 某命令)"""
    from typer.main import get_command

    from prism import cli
    from prism.cli import stock as _stock
    from prism.stock.command._registry import USAGE

    words = [a for a in argv if not a.startswith('-')]
    node, parent, path = get_command(cli.app.app), None, []
    # 按 click 里真实注册的往下走, 不查 COMMANDS 表 —— pydata/config 这类
    # 非股票命令只挂在 app 上, 表里没有; position/config 还是嵌套组
    while words and words[0] in getattr(node, 'commands', {}):
        parent, node = node, node.commands[words.pop(0)]
        path.append(node.name)
        if not hasattr(node, 'commands'):
            break
    if path:
        if hasattr(node, 'commands'):        # 停在组上: 列子动作
            return render_group(node, 'prism ' + ' '.join(path))
        prefix = ('prism ' + ' '.join(path[:-1])).strip()
        return render_cmd(parent, node.name, prefix)
    return render_root(USAGE, panels or {}, _stock.COMMANDS)


def wants_help(argv):
    return any(a in ('-h', '--help') for a in argv if a.startswith('-'))
