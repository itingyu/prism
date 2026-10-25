"""文档不走样：docs/commands.md 必须与命令注册表一致。

命令改名/加参数却忘了重新生成，这里会红；修法就是跑一次生成脚本。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_commands_doc_is_current():
    p = subprocess.run([sys.executable, str(ROOT / 'tools' / 'gen_docs.py'), '--check'],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, (p.stdout + p.stderr).strip()


def test_every_doc_link_resolves():
    """docs/ 里的相对链接必须指向真实文件，别留死链"""
    import re

    docs = ROOT / 'docs'
    bad = []
    for md in list(docs.glob('*.md')) + [ROOT / 'README.md']:
        text = md.read_text(encoding='utf-8')
        for link in re.findall(r'\]\((?!https?:|#)([^)#]+)', text):
            target = (md.parent / link).resolve()
            if not target.exists():
                bad.append(f'{md.name} → {link}')
    assert not bad, '死链: ' + ', '.join(bad)


def test_readme_numbers_match_registry():
    """README 里的规模数字不能凭记忆写"""
    from prism.cli.stock import COMMANDS
    from prism.stock.bridge.ak_families import FAM
    from prism.stock.command._schema import kind_list

    total = sum(kind_list(c, FAM)['kinds_count'] for c in COMMANDS if c in FAM)
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert f'{len(COMMANDS)} 个命令' in text, f'README 未写 {len(COMMANDS)} 个命令'
    assert f'{total} 个扩展口径' in text, f'README 未写 {total} 个扩展口径'
