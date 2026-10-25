"""prism CLI 入口: 顶层就是动作 (prism quote / prism pool / ...) + prism pydata

本仓只做股票一件事, 所以没有 `prism stock` 这一层 —— 动作直接是顶层命令。
历史写法 `prism stock <动作>` 仍可用 (见 main() 里的兼容改写), 但会打一行提示。
"""
import sys

import typer

from prism import __version__
from prism.cli import config_cmd as _config_cmd
from prism.cli import helptext as _helptext
from prism.cli import pydata as _pydata
from prism.cli import stock as _stock
from prism.cli.runtime import Fmt, Output, _CTX
from prism.stock.command._registry import USAGE

app = typer.Typer(
    add_completion=True, no_args_is_help=False,
    # rich 排版只在 help 里被接管掉还不够: 用法错误、未捕获异常也会画成
    # 带边框的面板 (窄终端折行、`grep` 不到)。这两个开关把 typer 的 rich
    # 通道整个关掉, 输出退回纯文本。
    rich_markup_mode=None, pretty_exceptions_enable=False,
    help='prism: 股票行情/涨停/资金/新闻/财报/K线/选股/持仓 (顶层即动作, 无参看目录)',
    context_settings={'help_option_names': ['-h', '--help']})

# 顶层命令按用途分面板, `prism --help` 一屏看完所有动作。
# 面板里的名字只是分组的意图, 真正注册的是 COMMANDS —— 名字对不上就跳过,
# 没进任何面板的命令统一进 '其他', 保证新命令不会在帮助里消失。
_PANELS = {
    '行情与数据': ('quote', 'pool', 'check', 'calendar', 'flow', 'news',
                   'announcement', 'financials', 'valuation', 'patterns', 'boards',
                   'hk-quote', 'us-quote', 'kr-quote'),
    '分析与选股': ('analyze', 'screen', 'risk', 'report', 'excel', 'sentiment', 'diagram'),
    '图表': ('kline', 'intraday', 'hk-kline', 'us-kline', 'kr-kline'),
    '财务与要素': ('income', 'balance', 'cashflow', 'company', 'business', 'holders',
                   'industry', 'concept', 'dividend', 'margin', 'screener', 'ipo',
                   'index', 'forecast', 'dupont', 'growth'),
    '事件与宏观': ('lhb', 'block-trade', 'unlock', 'survey', 'holder-count',
                   'analyst-report', 'earnings-preview', 'pledge', 'goodwill',
                   'rating', 'comment', 'macro', 'stock-connect', 'breadth', 'cb',
                   'etf', 'changes', 'hot', 'buyback', 'notice', 'shares',
                   'disclosure-schedule', 'earnings-report', 'fhps',
                   'shareholding-change', 'insider-trade',
                   'futures', 'option', 'fund', 'bond', 'hk',
                   'spot', 'world', 'misc'),
    '取数入口与自描述': ('lookup', 'schema'),
}
_PANELS = {p: tuple(n for n in names if n in _stock.COMMANDS)
           for p, names in _PANELS.items()}
_PANELS = {p: n for p, n in _PANELS.items() if n}
_PANEL_OF = {n: p for p, names in _PANELS.items() for n in names}
for _name, _fn in _stock.COMMANDS.items():
    app.command(_name, rich_help_panel=_PANEL_OF.get(_name), **_stock.CMD_OPTS.get(_name, {}))(_fn)
app.add_typer(_stock.position_app, name='position', rich_help_panel='持仓')
app.add_typer(_config_cmd.app, name='config', rich_help_panel='透传与工具')
app.command('pydata', rich_help_panel='透传与工具')(_pydata.pydata_cmd)


def _version(value: bool):
    if value:
        print(f'prism {__version__}')
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context,
          version: bool = typer.Option(
              False, '--version', '-V', callback=_version, is_eager=True,
              help='显示版本'),
          fmt: str = Fmt, output: str = Output):
    """股票数据与选股工具 (自带网络层)"""
    _CTX['stock_fmt'] = fmt
    _CTX['stock_output'] = output
    if ctx.invoked_subcommand is None:
        print(_helptext.render_root(USAGE, _PANELS, _stock.COMMANDS))
        raise typer.Exit(code=0)



def _global_flags(argv):
    """摘掉全局 -d/--debug 与 --log-file, 返回 (debug 档位, 日志文件, 剩余 argv)

    这两个是**全局**的: 放在命令前后都认 (`prism -d quote 600519` 与
    `prism quote 600519 -d` 等价), 所以必须在 typer 解析之前拿走。
    -d 可叠加: -d 本仓 DEBUG, -dd 连三方库也 DEBUG。
    """
    rest, dbg, log_file = [], 0, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('-d', '--debug'):
            dbg += 1
        elif a.startswith('--debug='):
            v = a.split('=', 1)[1]
            dbg = int(v) if v.isdigit() else 1
        elif a == '--log-file':
            i += 1
            log_file = argv[i] if i < len(argv) else None
        elif a.startswith('--log-file='):
            log_file = a.split('=', 1)[1]
        elif a.startswith('-') and not a.startswith('--') and len(a) > 1 \
                and set(a[1:]) == {'d'}:
            dbg += len(a) - 1          # -dd
        else:
            rest.append(a)
        i += 1
    return dbg, log_file, rest


def main():
    # 日志必须最先装配: 装配前 logger 会走 Python 的 lastResort, 把 WARNING
    # 裸打到 stderr, 既没级别也没格式; 装配后默认 WARNING = 静默, -d 才出声。
    from prism.core.logging import env_debug as _env_debug
    from prism.core.logging import setup as _setup_logging

    argv = sys.argv[1:]
    _dbg, _lf, argv = _global_flags(argv)
    _setup_logging(debug=_dbg + _env_debug(), log_file=_lf)
    if argv and argv[0] == 'stock':
        # 旧写法兼容: prism stock quote -> prism quote
        print('[弃用] `prism stock` 已扁平化, 改用 `prism <动作>` (例: prism quote 600519)',
              file=sys.stderr)
        argv = argv[1:]
    # -h/--help 不交给 typer: 它用 rich 表格排版, 窄终端会折行 + 画框,
    # 85 个命令要滚一屏半。这里直接出纯文本 (见 helptext.py)。
    if _helptext.wants_help(argv):
        print(_helptext.render(argv, _PANELS))
        raise SystemExit(0)
    # 命令组裸跑 (prism config / prism position) 也走同一套纯文本,
    # 而不是 typer 的 "Options:/Commands:" 长格式
    if argv and argv[0] in ('config', 'position') and not [
            a for a in argv[1:] if not a.startswith('-')]:
        print(_helptext.render(argv, _PANELS))
        raise SystemExit(0)
    sys.argv = [sys.argv[0]] + argv
    app()


if __name__ == '__main__':
    main()
