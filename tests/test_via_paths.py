"""专用命令与 --kind 口径不能给出两套结果 (不联网)

背景: 同一个上游接口有两条入口 —— `prism lhb` (专用) 与
`prism lhb --kind stock_lhb_detail_em` (通用口径)。历史上两条路径各自算
取数窗口, 通用路径没给 start_date/end_date 就吃到上游的旧默认窗口,
静默返回三年前的数据。窗口逻辑合并后风险降低了, 但"某天又各写一遍"这种
退化不会有任何报错 —— 所以这里把两条路径实际传给上游的参数录下来比对。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from prism.stock.bridge.ak_families import FAM  # noqa: E402
from prism.stock.bridge.ak_via import INTERFACE_VIA  # noqa: E402
from prism.stock.command import _actions_ak as A  # noqa: E402


class Recorder:
    """替掉 bridge 的 rows(), 只记录上游接口与参数"""

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload if payload is not None else [{'代码': '600519'}]

    def __call__(self, name, timeout=60, **params):
        self.calls.append((name, params))
        return self.payload


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    monkeypatch.setattr(A._ak, '_akb_rows_patch_marker', True, raising=False)
    from prism.stock.bridge import ak as akb
    monkeypatch.setattr(akb, 'rows', r)
    return r


def _args(**kw):
    base = dict(family=None, kind=None, indicator=None, limit=50,
                days=None, start=None, end=None, code=None, codes=None,
                stats=None, yyb=False, source=None, arg=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_lhb_special_and_kind_share_window(rec):
    """专用路径与口径路径必须传同一组 start_date/end_date"""
    A._act_lhb(_args(days=7), {})
    special = rec.calls[-1]
    A._act_fam(_args(family='lhb', kind='stock_lhb_detail_em', days=7), {})
    kind = rec.calls[-1]
    assert special[0] == kind[0] == 'stock_lhb_detail_em'
    assert special[1]['start_date'] == kind[1]['start_date']
    assert special[1]['end_date'] == kind[1]['end_date']


def test_unlock_special_and_kind_share_window(rec):
    A._act_unlock(_args(days=30), {})
    special = rec.calls[-1]
    A._act_fam(_args(family='unlock', kind='stock_restricted_release_detail_em',
                     days=30), {})
    kind = rec.calls[-1]
    assert special[0] == kind[0] == 'stock_restricted_release_detail_em'
    assert special[1]['start_date'] == kind[1]['start_date']
    assert special[1]['end_date'] == kind[1]['end_date']


def test_interval_interfaces_always_get_a_window(rec):
    """区间型接口一律显式给窗口 —— 这是当年静默返回 2023 年数据的根因

    抽所有族 × 所有口径: 只要接口签名里有 start_date/end_date, 两条都必须
    有值, 不能指望上游默认窗口 (那是几年前的)。
    """
    checked = 0
    for fam, kinds in FAM.items():
        for kind in kinds:
            try:
                A._act_fam(_args(family=fam, kind=kind, days=30), {})
            except Exception:
                # 缺必填参数 / 上游失效 的接口不在本条射程内
                continue
            if not rec.calls:
                continue
            name, params = rec.calls[-1]
            if 'start_date' in params or 'end_date' in params:
                # 有的接口只收 start_date (如中美国债, 省略结束日 = 到今天),
                # 关键是别一个都不给 —— 那才会吃到上游的旧默认窗口
                assert params.get('start_date') or params.get('end_date'), \
                    f'{name} 一个日期都没注入'
                checked += 1
    assert checked > 20, f'只验证到 {checked} 个区间型接口, 覆盖可疑'


def test_via_map_points_at_real_commands():
    """INTERFACE_VIA 指向的命令/接口都必须真实存在, 否则是写死的死引用

    映射是"接口 → 专用命令", 专用命令不一定是该接口的口径入口
    (如 stock_dzjy_mrmx 的专用命令是 block-trade, 但它的口径是 dzjy_mrtj 等),
    所以只校验: 命令在注册表且在口径族里, 接口本身收录在某个族里。
    """
    from prism.cli.stock import COMMANDS
    all_kinds = {k for kinds in FAM.values() for k in kinds}
    for iface, (cmd, flags) in INTERFACE_VIA.items():
        assert cmd in COMMANDS, f'{iface} 指向不存在的命令 {cmd}'
        assert iface in all_kinds, f'{iface} 不在任何口径族里'
        if cmd in FAM:
            assert FAM[cmd], f'{iface} 指向的命令 {cmd} 口径族是空的'
        assert isinstance(flags, dict)
