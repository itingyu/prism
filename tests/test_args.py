"""分发参数 Args 的护栏 (不联网)

Args 取代了原来的 `_DEFAULTS` 字典 + SimpleNamespace。这里的测试守三件事:
- 默认值与改造前的取值一致 (差了就是全网行为漂移)
- 拼错的字段名当场报错, 而不是运行到那行才炸
- 命令签名里的每个参数都写得起 (否则新命令的选项会被静默丢掉)
"""
import ast
import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from prism.cli.stock import COMMANDS  # noqa: E402
from prism.stock.command._args import _DYNAMIC, Args, build  # noqa: E402


@pytest.mark.parametrize('name,value', [
    ('scope', 'industry'), ('pool', 'short'), ('min_score', 60),
    ('limit', 10), ('bars', 120), ('days', 30), ('period', 'day'),
    ('lib', 'akshare'), ('by', 'source'), ('ma_daily', '5,10,20,60'),
    ('bar_seconds', 60), ('timeout', 60.0), ('http_timeout', 20.0),
])
def test_defaults_unchanged(name, value):
    """默认值是全网行为的一部分: 改一个数字就等于改所有命令的结果"""
    assert getattr(Args(), name) == value


def test_unknown_field_write_is_rejected():
    """字段名写错要当场报错, 不能悄悄变成一个死字段"""
    a = Args()
    with pytest.raises(AttributeError):
        a.min_scroe = 80


def test_dynamic_fields_are_writable():
    """命令签名/显式分发带来的字段必须能写"""
    a = Args()
    for name in ('family', 'stats', 'yyb', 'list_kinds', 'source'):
        assert name in _DYNAMIC
        setattr(a, name, None)


def test_mutable_defaults_not_shared():
    a, b = Args(), Args()
    a.codes.append('600519')
    a.form['k'] = 'v'
    assert b.codes == [] and b.form == {}


def test_build_skips_none_and_copies_lists():
    src = ['600519']
    a = build(codes=src, stats=None, keyword='x')
    assert a.codes == ['600519'] and a.codes is not src
    assert a.keyword == 'x'
    assert not hasattr(a, 'stats') or a.stats is None


def test_every_command_param_is_writable():
    """79 条命令的每个参数都要能写进 Args

    漏一个的后果是那条命令运行到 setattr 时 AttributeError —— 也就是
    "这条命令整个不能用"。所以从真实命令签名扫一遍, 不靠人工登记。
    """
    from dataclasses import fields
    declared = {f.name for f in fields(Args)}
    missing = set()
    for name, fn in COMMANDS.items():
        for p in inspect.signature(fn).parameters:
            if p not in declared and p not in _DYNAMIC:
                missing.add(p)
    assert not missing, f'这些命令参数写不进 Args: {sorted(missing)}'


def test_every_dispatch_kw_is_writable():
    """显式分发 _dispatch(..., key=value) 的每个 key 都要能写"""
    from dataclasses import fields
    declared = {f.name for f in fields(Args)}
    missing = set()
    for path in (ROOT / 'src/prism').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == '_dispatch'):
                for kw in node.keywords:
                    if kw.arg and kw.arg not in declared and kw.arg not in _DYNAMIC:
                        missing.add(kw.arg)
    assert not missing, f'这些分发参数写不进 Args: {sorted(missing)}'
