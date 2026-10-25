"""帮助输出形态: 纯文本、不折行、不重复

typer 默认的 rich 表格在窄终端会把说明折成多行、加边框, 85 个命令滚一屏半,
也没法 grep。cli/helptext.py 接管 -h 后这些约束要一直成立, 否则改回表格
也没人会注意到。
"""
import shutil
import subprocess

import pytest

# 用装好的 console script: 包没有 __main__, `python -m prism` 起不来
_PRISM = shutil.which('prism') or 'prism'


def run(*args):
    p = subprocess.run([_PRISM, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def test_root_help_is_plain_text():
    rc, out, _ = run('-h')
    assert rc == 0
    for box in '╭╮╰╯│─':
        assert box not in out, f'出现了表格边框字符 {box!r}'
    assert '[default:' not in out
    assert 'Show this message' not in out
    assert '--install-completion' not in out
    assert out.startswith('用法: prism')


def test_root_help_lists_commands_compactly():
    rc, out, _ = run('-h')
    names = ['quote', 'kline', 'pool', 'lookup', 'schema']
    for n in names:
        assert n in out
    # 密排: 85 条命令不该一条一行
    assert len(out.splitlines()) < 60, '顶层帮助过长, 说明又退回逐条展开了'


def test_command_help_shows_usage_and_flags():
    rc, out, _ = run('kline', '-h')
    assert rc == 0
    assert out.splitlines()[0].startswith('用法: prism kline')
    assert '--chart' in out
    assert '--bars <int>' in out
    for box in '╭╮╰╯':
        assert box not in out


def test_command_help_has_no_wrapped_description():
    """一行一个选项: 说明不折行 (折行是 rich 表格的老毛病)"""
    rc, out, _ = run('kline', '-h')
    assert rc == 0
    for line in out.splitlines():
        assert not line.endswith(' '), f'疑似折行残留: {line!r}'


def test_help_flag_works_after_positional():
    rc, out, _ = run('quote', '600519', '-h')
    assert rc == 0
    assert out.startswith('用法: prism quote')


def test_position_subcommands_are_listed():
    rc, out, _ = run('position', '-h')
    assert rc == 0
    for sub in ('add', 'list', 'remove'):
        assert sub in out


@pytest.mark.parametrize('cmd', ['pydata', 'schema'])
def test_non_stock_commands_have_help(cmd):
    rc, out, _ = run(cmd, '-h')
    assert rc == 0
    assert out.startswith(f'用法: prism {cmd}')


def test_unknown_command_falls_back_to_root_help():
    rc, out, _ = run('nosuch-command', '-h')
    assert rc == 0
    assert out.startswith('用法: prism')
