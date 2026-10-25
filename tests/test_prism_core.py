"""prism 核心行为测试 (不联网)

覆盖这几处最容易悄悄坏掉的地方:
- 通用口径路径的取数窗口 (漏注入就静默返回过期数据)
- JSON 信封 (ok/source/count/rows 必须齐)
- 主语参数提取 (命令位置参数叫法不一, 提取口径必须统一)
- 注册表守卫 (命令/动作/口径/面板之间不能漂移)
- 帮助文本不能指向已删除的命令

跑: PYTHONPATH=src python -m pytest tests -q
"""
import inspect
import sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.models import OptionInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from prism.cli.stock import COMMANDS  # noqa: E402
from prism.stock.command._common import subject, subject_one  # noqa: E402
from prism.stock.command._envelope import envelope  # noqa: E402
from prism.stock.command._registry import ACTIONS, USAGE  # noqa: E402


# ── JSON 信封 ────────────────────────────────────────────────────
def test_envelope_list_payload():
    env = envelope([{'a': 1}, {'a': 2}])
    assert env['ok'] is True
    assert env['count'] == 2
    assert env['rows'] == [{'a': 1}, {'a': 2}]


def test_envelope_dict_payload_keeps_original_keys():
    env = envelope({'今天': '2026-10-26', '是否交易日': True})
    assert env['ok'] is True
    assert env['今天'] == '2026-10-26'          # 原键保留, 老脚本读得到
    assert list(env)[0] == 'ok'                # 标准键排前面


def test_envelope_unifies_table_containers():
    env = envelope({'data': {'items': [{'x': 1}]}})
    assert env['rows'] == [{'x': 1}]           # data.items 并到 rows
    assert env['count'] == 1


def test_envelope_source_alias():
    env = envelope([{'源': 'tencent'}])
    assert env['rows'][0]['源'] == 'tencent'


def test_envelope_keeps_false_ok():
    assert envelope({'ok': False})['ok'] is False


# ── 主语参数 ─────────────────────────────────────────────────────
def test_subject_prefers_codes():
    a = SimpleNamespace(codes=['600519'], code='000001', symbol='AAPL')
    assert subject(a) == ['600519']
    assert subject_one(a) == '600519'


def test_subject_falls_back_to_code_then_symbol():
    assert subject(SimpleNamespace(code='000001')) == ['000001']
    assert subject(SimpleNamespace(symbol='AAPL')) == ['AAPL']
    assert subject(SimpleNamespace()) == []


def test_subject_skips_empty_codes():
    assert subject(SimpleNamespace(codes=[], code='600519')) == ['600519']


# ── 取数窗口 ─────────────────────────────────────────────────────
def test_date_window_uses_days(monkeypatch):
    from prism.stock.command import _actions_ak as A
    from prism.stock.bridge import ak as akb
    monkeypatch.setattr(akb, 'ymd', lambda d=None: '20261026')
    monkeypatch.setattr(akb, '_shift', lambda d, n: '20260926')
    args = SimpleNamespace(days=30, start=None, end=None)
    assert A._date_window(args) == ('20260926', '20261026')


def test_date_window_explicit_start_end(monkeypatch):
    from prism.stock.command import _actions_ak as A
    from prism.stock.bridge import ak as akb
    monkeypatch.setattr(akb, 'ymd', lambda d=None: (
        '20260101' if d == '20260101' else '20261026'))
    monkeypatch.setattr(akb, '_shift', lambda d, n: '20260926')
    args = SimpleNamespace(days=30, start='20260101', end=None)
    assert A._date_window(args)[0] == '20260101'


def test_fam_injects_window_for_range_interfaces(monkeypatch):
    """区间型接口必须注入 start_date/end_date

    漏注入就直接吃上游默认窗口 (实测返回 2023 年的数据, 不报错)。
    """
    from prism.stock.command import _actions_ak as A
    from prism.stock.bridge import ak as akb

    seen = {}

    def fake_rows(func, timeout=90, **params):
        seen.update(params)
        return [{'代码': '000011', '上榜日': '2026-10-22'}]

    monkeypatch.setattr(akb, 'rows', fake_rows)
    monkeypatch.setattr(akb, 'ymd', lambda d=None: '20261026')
    monkeypatch.setattr(akb, '_shift', lambda d, n: '20261019')
    args = SimpleNamespace(family='lhb', kind='stock_lhb_detail_em',
                           codes=[], limit=5, params=[], date=None,
                           days=7, start=None, end=None)
    out = A._act_fam(args, {})
    assert seen.get('start_date') == '20261019'
    assert seen.get('end_date') == '20261026'
    assert out.get('date') == '2026-10-19~2026-10-26'   # 窗口必须出现在结果里


# ── 注册表守卫 ───────────────────────────────────────────────────
def test_every_command_has_docstring():
    missing = [n for n, fn in COMMANDS.items()
               if not (fn.__doc__ or '').strip()]
    assert not missing, f'命令缺说明: {missing}'


def test_every_action_is_callable():
    bad = [k for k, v in ACTIONS.items() if not callable(v)]
    assert not bad, f'动作不可调用: {bad}'


def test_command_signatures_are_inspectable():
    for name, fn in COMMANDS.items():
        sig = inspect.signature(fn)
        assert sig.parameters, f'{name} 没有可读签名'


def test_family_via_mapping_points_at_real_commands():
    from prism.stock.bridge.ak_via import INTERFACE_VIA
    bad = {i: c for i, (c, _) in INTERFACE_VIA.items() if c not in COMMANDS}
    assert not bad, f'映射指向不存在的命令: {bad}'


def test_family_kinds_exist_in_fam():
    from prism.stock.bridge.ak_families import FAM
    assert FAM, '口径表空了'
    for fam, spec in FAM.items():
        for name, s in spec.items():
            assert s.get('n'), f'{fam}/{name} 缺接口名'


# ── 帮助文本 ─────────────────────────────────────────────────────
def test_usage_has_no_dangling_commands():
    """帮助里不能出现已删除的命令 (data call / prism sources 等)"""
    for gone in ('data call', 'data url', 'data health', 'prism sources',
                 'prism commands', 'prism tools'):
        assert gone not in USAGE, f'USAGE 还指着已删除的命令: {gone}'


# ---------------------------------------------------------------- 选项规格
#
# 全仓只认这几条, 新增命令必须遵守:
#   --kind    口径 (akshare 扩展口径); 有 --kind 必有 --list
#   --type    有限枚举的类型 (池类型 / 公告类型 / 图类型 / 变化类型)
#   --source  数据源方法        --arg  底层接口额外参数 K=V
#   -n/--limit 条数             --bars K 线根数 / 回看根数
#   -o/--output 输出路径        --ascii-style 字符画风格

_SPEC_FLAGS = {
    '--kind': 'kind', '--list': 'list_kinds', '--type': 'type_',
    '--source': 'source', '--arg': 'arg', '--limit': 'limit',
    '--bars': 'bars', '--output': 'output', '--ascii-style': 'ascii_style',
}


def _cmd_flags():
    """每个命令的 {flag: 参数名}"""
    out = {}
    for name, fn in COMMANDS.items():
        flags = {}
        for p in inspect.signature(fn).parameters.values():
            d = p.default
            if isinstance(d, OptionInfo):
                for decl in (d.param_decls or ()):
                    if decl.startswith('--'):
                        flags[decl] = p.name
        out[name] = flags
    return out


def test_flag_maps_to_one_param_name():
    """同一个 flag 在不同命令里必须指向同名参数

    否则 '这个选项到底叫什么' 每个命令都不一样, 脚本没法通用处理。
    """
    seen = {}
    for cmd, flags in _cmd_flags().items():
        for flag, param in flags.items():
            seen.setdefault(flag, {}).setdefault(param, []).append(cmd)
    bad = {f: sorted(p) for f, p in seen.items() if len(p) > 1}
    assert not bad, f'同一 flag 对应多个参数名: {bad}'


def test_kind_always_has_list():
    """有 --kind 的命令必须有 --list

    否则用户拿到一个可枚举的口径名, 却没法知道有哪些 —— 只能去翻源码。
    """
    flags = _cmd_flags()
    missing = [c for c, f in flags.items() if '--kind' in f and '--list' not in f]
    assert not missing, f'这些命令有 --kind 却没有 --list: {missing}'


def test_short_flags_have_fixed_meaning():
    """短标志含义固定: -f 格式 / -n 条数 / -o 输出路径"""
    seen = {}
    for cmd, flags in _cmd_flags().items():
        for p in inspect.signature(COMMANDS[cmd]).parameters.values():
            d = p.default
            if isinstance(d, OptionInfo):
                for decl in (d.param_decls or ()):
                    if len(decl) == 2 and decl.startswith('-') and not decl.startswith('--'):
                        seen.setdefault(decl, set()).add(p.name)
    assert seen.get('-n') == {'limit'}, f'-n 必须是条数, 实际 {seen.get("-n")}'
    assert seen.get('-f') == {'fmt'}, f'-f 必须是输出格式, 实际 {seen.get("-f")}'
    assert seen.get('-o') == {'output'}, f'-o 必须是输出路径, 实际 {seen.get("-o")}'


def test_spec_flags_use_canonical_param_names():
    """规格里的选项必须用约定的参数名"""
    for cmd, flags in _cmd_flags().items():
        for flag, param in _SPEC_FLAGS.items():
            if flag in flags:
                assert flags[flag] == param, (
                    f'{cmd} 的 {flag} 参数名是 {flags[flag]}, 应为 {param}')


def test_no_dead_options():
    """不能有"读了没人提供"的选项

    动作里 getattr(args, 'x') 取的字段, 必须有命令真的提供这个选项,
    否则是名存实亡的空选项 (改前 ascii_plain/ascii_wide/ascii_gap 就是)。
    """
    import ast
    from prism.cli import stock as cli_stock

    defaults = set()
    explicit = set()
    tree = ast.parse(Path(cli_stock.__file__).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and getattr(node.targets[0], 'id', '') == '_DEFAULTS'):
            defaults = {k.value for k in node.value.keys}
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == '_dispatch'):
            for kw in node.keywords:
                if kw.arg:
                    explicit.add(kw.arg)
    provided = defaults | explicit
    for fn in COMMANDS.values():
        provided |= set(inspect.signature(fn).parameters)

    reads = set()
    for p in Path('src/prism/stock/command').rglob('*.py'):
        t = ast.parse(p.read_text(encoding='utf-8'))
        for node in ast.walk(t):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'getattr' and len(node.args) == 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == 'args'
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)):
                reads.add(node.args[1].value)
    known = {'arg', 'list_kinds', 'kind', 'source', 'fmt', 'output', 'format'}
    gap = sorted(reads - provided - known)
    assert not gap, f'动作读了但没人提供的字段: {gap}'


def test_action_fields_are_provided():
    """动作读的 args 字段必须有人提供

    args 命名空间 = Args 的字段 + 命令签名参数 + 显式分发的参数 + 动作自己
    赋的字段。少任何一样, 该字段就被静默丢掉 (表现为"选项传了没反应"),
    这类洞靠肉眼极难发现 —— 所以静态扫一遍: 动作里读到的每个 args 字段
    都要能说明来源。
    """
    import ast

    from prism.stock.command._args import Args

    defaults = {f.name for f in fields(Args)}
    explicit = set()
    for path in Path('src/prism').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == '_dispatch'):
                for kw in node.keywords:
                    if kw.arg:
                        explicit.add(kw.arg)

    reads, assigned = set(), set()
    for path in Path('src/prism/stock/command').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == 'args'):
                reads.add(node.attr)
                assigned.add(node.attr)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'getattr' and len(node.args) > 1
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == 'args'
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)):
                # 带默认值的 getattr 不会因字段缺失而失败, 不算缺口
                if len(node.args) < 3:
                    reads.add(node.args[1].value)

    cmd_params = set()
    for fn in COMMANDS.values():
        cmd_params |= set(inspect.signature(fn).parameters)
    injected = {'arg', 'list_kinds', 'kind', 'source', 'fmt', 'output',
                'format'}
    # 动作自己读又自己写的字段 (中间变量) 不算缺口
    self_set = set()
    for path in Path('src/prism/stock/command').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute)
                    and isinstance(node.targets[0].value, ast.Name)
                    and node.targets[0].value.id == 'args'):
                self_set.add(node.targets[0].attr)

    gap = sorted(reads - defaults - explicit - cmd_params - injected - self_set)
    assert not gap, f'动作读了没人提供的 args 字段: {gap}'


def test_source_option_help_points_at_real_command():
    from prism.cli import stock as cli_stock
    src = Path(cli_stock.__file__).read_text(encoding='utf-8')
    assert 'prism sources' not in src


# --- 声明式命令 (cli/spec.py) ---

def test_spec_built_command_signature():
    """build() 造出的函数签名必须被 typer 正确内省"""
    import inspect
    from prism.cli.spec import Arg, Cmd, Opt, build

    fake = lambda **kw: None
    fn = build(Cmd('demo', fake, '演示',
                   args=(Arg('code', '代码', multiple=True, required=False),),
                   opts=(Opt('--bars', type=int, default=7, help='根数'),
                         Opt('--plain', dest='ascii_art', type=bool, default=False,
                             help='纯文本'))))
    sig = inspect.signature(fn)
    assert sig.parameters['bars'].default.default == 7
    assert sig.parameters['bars'].annotation is int
    assert sig.parameters['ascii_art'].default.param_decls == ('--plain',)
    assert sig.parameters['code'].default.default is None
    assert fn.__doc__ == '演示'
    assert fn.__name__ == '_demo'


def test_spec_signature_matches_action():
    """声明式命令: 签名里的每个参数, 动作函数都得接得住

    这是声明式改造最容易断的地方 —— 改了 Opt 名字但没改动作签名,
    import 不会报错, 只有用户真跑那条命令才 TypeError。
    """
    import inspect
    from prism.cli import stock
    from prism.cli.spec import spec_of

    checked = 0
    for name in stock.COMMANDS:
        spec = spec_of(name)
        if spec is None:
            continue
        # 只校验 spec 声明的参数; --source/--limit 由 cmd 装饰器统一注入
        declared = [a.name for a in spec.args] + [o.name for o in spec.opts]
        dummy = {}
        for a in spec.args:
            dummy[a.name] = [] if a.multiple else None
        for o in spec.opts:
            dummy[o.name] = [] if o.multiple else o.default
        try:
            inspect.signature(spec.action).bind(**dummy)
        except TypeError as e:
            pytest.fail(f'{name}: 签名与动作不匹配 — {e}')
        checked += 1
    assert checked, '没有命令使用声明式定义'


def test_spec_help_matches_docstring():
    """help 段落的说明必须来自 spec.help, 不能空"""
    from prism.cli import stock
    from prism.cli.spec import spec_of
    for name, fn in stock.COMMANDS.items():
        spec = spec_of(name)
        if spec is None:
            continue
        assert fn.__doc__ == spec.help, name
        assert spec.help.strip(), name


def test_all_commands_are_declared():
    """所有命令都必须走声明式定义 (cli/spec.py)

    混用两种写法会让"选项即数据"的保证只覆盖一半 —— 测试、schema、
    文档生成都从 spec 读, 漏掉一条就静默失明。
    """
    from prism.cli import stock
    from prism.cli.spec import spec_of

    missing = [n for n in stock.COMMANDS if spec_of(n) is None]
    assert not missing, f'这些命令还是装饰器写法: {missing}'
