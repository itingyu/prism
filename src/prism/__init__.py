"""prism: 股票数据与选股 CLI"""
# 版本号单一真源是 pyproject.toml 的 project.version (见 core/version.py),
# 不在这里硬编码 —— 硬编码的那份自 0.20.0 起就没跟上, `prism --version`
# 会显示过期版本, 排障时直接误导。
from prism.core.version import get_version

__version__ = get_version()
