"""命令组裸跑 / 出错信息 / 排序缺值 的回归护栏 (不联网)

三件事各自对应一次真实故障:
- `prism concept` 裸跑崩 "missing 3 required positional arguments" ——
  装饰器把可选参数从 kw 里摘走, 动作签名却没变短
- `prism config` 裸跑出 typer 的 rich 表格帮助 (带边框, 窄终端折行)
- `prism comment` 遇上游 None 抛 "< not supported between NoneType and float"
"""
import shutil
import subprocess

import pytest

_PRISM = shutil.which('prism') or 'prism'


def run(*args):
    p = subprocess.run([_PRISM, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


@pytest.mark.parametrize('group', ['config', 'position'])
def test_bare_group_prints_plain_help(group):
    rc, out, err = run(group)
    assert rc == 0
    text = out + err
    for box in '╭╮╰╯│─':
        assert box not in text, f'{group} 的帮助里出现了表格边框 {box!r}'
    assert text.startswith(f'用法: prism {group}')
    assert 'Show this message' not in text


def test_usage_error_is_plain_text():
    """缺参数时的报错不能用 rich 面板 (grep 不到、窄终端折行)"""
    rc, out, err = run('check')
    text = out + err
    assert rc != 0
    for box in '╭╮╰╯│─':
        assert box not in text, f'报错里出现表格边框 {box!r}'
    assert 'codes' in text


def test_sort_rows_puts_missing_last():
    """上游缺值排最后, 不参与比较 —— 不许抛 TypeError"""
    from prism.util.num import sort_rows
    rows = [{'g': '1.5'}, {'g': None}, {'g': '9'}, {'g': ''}, {'g': 3}]
    got = [r['g'] for r in sort_rows(rows, 'g')]
    assert got[:3] == ['9', 3, '1.5']
    assert got[3:] in ([None, ''], ['', None])


def test_sort_rows_asc_and_empty():
    from prism.util.num import sort_rows
    rows = [{'g': '2'}, {'g': None}, {'g': '1'}]
    assert [r['g'] for r in sort_rows(rows, 'g', desc=False)] == ['1', '2', None]
    assert sort_rows([], 'g') == []
    assert sort_rows([{'x': 1}], 'g') == [{'x': 1}]


def test_build_fills_declared_defaults():
    """spec 声明的默认值必须补进动作调用 —— 漏了就是整条命令不可用"""
    from prism.cli.spec import Arg, Cmd, Opt, build

    seen = {}

    def act(code, limit, kind, list_kinds, arg):
        seen.update(code=code, limit=limit, kind=kind,
                    list_kinds=list_kinds, arg=arg)
        return 'ok'

    spec = Cmd('demo', act, 'demo',
               args=(Arg('code', required=False),),
               opts=(Opt('--limit', type=int, default=10),
                     Opt('--kind'), Opt('--list', dest='list_kinds', type=bool,
                                        default=False),
                     Opt('--arg', default=None, multiple=True)))
    fn = build(spec)
    assert fn() == 'ok'
    assert seen == {'code': None, 'limit': 10, 'kind': None,
                    'list_kinds': False, 'arg': None}
