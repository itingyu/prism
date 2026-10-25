"""文档里的规模数字与命令引用必须跟代码一致。

README / docs 最容易腐烂的不是图，是"79 个命令""163 个方法"这类手写数字，
以及改了命令名忘了改文档里的示例。这里把它们全部从代码算出来对拍。
"""
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ([ROOT / 'README.md'] + sorted((ROOT / 'docs').glob('*.md'))
        + sorted((ROOT / 'skills').glob('*/SKILL.md')))


def _facts():
    from prism.cli.stock import COMMANDS
    from prism.stock.bridge.ak_families import FAM
    total = sum(len(v) for v in FAM.values())
    src = [c for c, fn in COMMANDS.items()
           if 'source' in inspect.signature(fn).parameters]
    return {
        'commands': len(COMMANDS),
        'kinds': total,
        'families': len(FAM),
        'with_source': len(src),
    }


def test_scale_numbers_are_true():
    """README 声称的规模 == 注册表实际规模"""
    f = _facts()
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    for key, label in (('commands', '个命令'), ('kinds', '个扩展口径')):
        assert f'{f[key]} {label}' in text, f'README 没写 {f[key]} {label}'


def test_source_command_count_is_true():
    """sources.md 的"27 个命令支持 --source"必须对得上签名"""
    f = _facts()
    text = (ROOT / 'docs' / 'sources.md').read_text(encoding='utf-8')
    assert f'{f["with_source"]} 个命令支持' in text, \
        f'sources.md 未写 {f["with_source"]} 个命令支持 --source'


def test_method_count_matches_lookup():
    """sources.md / architecture.md 的"163 个方法" == lookup 实际条数"""
    from prism.stock.bridge.rawapi import methods_by_source
    f = _facts()
    n = sum(len(v) for v in methods_by_source().values())
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert f'{n} 个数据源方法' in text, f'README 未写 {n} 个数据源方法'
    for name in ('sources.md', 'architecture.md'):
        body = (ROOT / 'docs' / name).read_text(encoding='utf-8')
        assert f'{n} 个方法' in body, f'{name} 未写 {n} 个方法'
    assert f["commands"] in (79,)


def test_doc_command_names_exist():
    """文档里每个 `prism <名字>` 都得是真命令（或子应用）"""
    import re

    from prism.cli.stock import COMMANDS

    # stock / data 这类只出现在"没有 prism stock 这一层"的说明句里,
    # 是刻意提到一个不存在的旧名字, 不算死引用
    subs = {'position', 'config', 'pydata', 'stock', 'data'}
    bad = []
    for md in DOCS:
        for name in set(re.findall(r'prism ([a-z][a-z0-9-]+)', md.read_text(encoding='utf-8'))):
            if name in COMMANDS or name in subs:
                continue
            bad.append(f'{md.name}: prism {name}')
    assert not bad, '文档引用了不存在的命令: ' + ', '.join(sorted(bad))
