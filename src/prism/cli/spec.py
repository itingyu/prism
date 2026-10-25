"""命令声明式定义: 一处写清 参数 / 选项 / 动作, 由它生成 typer 命令。

现在加一条命令要改 4-8 个文件: cli/stock.py 的函数签名、app.py 的面板、
_registry.py 的动作映射、ak_families.py 的口径、_actions_*.py 的实现。
  签名和 docstring 是纯样板, 却占 1364 行里的一大半, 且和动作实现分居两地。

spec 把"签名 + 说明 + 动作入口"收进一处, 由 build() 合成 typer 认得的函数
(用 __signature__ 造参, 不 exec 字符串)。面板与口径仍由注册表推导。
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

import typer


@dataclass(frozen=True)
class Arg:
    """位置参数"""
    name: str
    help: str = ''
    type: Any = str
    multiple: bool = False          # 收多个值 (list[str])
    required: bool = True
    default: Any = None             # required=False 时的默认值
    metavar: str | None = None


@dataclass(frozen=True)
class Opt:
    """选项; dest 默认由 flag 推导 (--only-buy -> only_buy)"""
    flag: str
    help: str = ''
    type: Any = str
    default: Any = None
    dest: str | None = None
    multiple: bool = False
    short: tuple[str, ...] = ()     # 额外短标志, 如 ('-f',)
    metavar: str | None = None

    @property
    def name(self) -> str:
        return self.dest or self.flag.lstrip('-').replace('-', '_')


@dataclass(frozen=True)
class Cmd:
    """一条命令: 动作怎么跑, 参数怎么收"""
    name: str
    action: Callable[..., Any]
    help: str
    args: tuple[Arg, ...] = ()
    opts: tuple[Opt, ...] = ()


_SPECS: dict[str, Cmd] = {}


def spec_of(name: str) -> Cmd | None:
    """按命令名取回声明 (工具与测试用; 未改声明式的命令返回 None)"""
    return _SPECS.get(name)


def _ann(o) -> Any:
    return list[o.type] if o.multiple else o.type


def build(spec: Cmd):
    """合成一个 typer 能内省的函数: 签名来自 spec, 调用转给 spec.action"""
    params = []
    for a in spec.args:
        params.append(inspect.Parameter(
            a.name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=typer.Argument(... if a.required else a.default,
                                  help=a.help, metavar=a.metavar),
            annotation=_ann(a)))
    for o in spec.opts:
        params.append(inspect.Parameter(
            o.name, inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(o.default, *o.short, o.flag, help=o.help,
                                 metavar=o.metavar),
            annotation=_ann(o)))

    # 命令没给的参数一律按声明补齐: 有装饰器会把可选参数从 kw 里摘走
    # (如 _with_kind 摘 kind/list_kinds/arg), 动作签名却不会因此变短。
    _declared = {a.name: a.default for a in spec.args}
    _declared.update({o.name: o.default for o in spec.opts})

    def _run(**kw):
        for k, v in _declared.items():
            kw.setdefault(k, v)
        return spec.action(**kw)

    _run.__signature__ = inspect.Signature(params)
    _run.__doc__ = spec.help
    _run.__name__ = '_' + spec.name.replace('-', '_')
    # typer 读 __annotations__ 定参数类型, 缺了会当 str
    _run.__annotations__ = {p.name: p.annotation for p in params}
    _SPECS[spec.name] = spec
    return _run


# 全仓一致的通用选项 (与 runtime.Fmt / runtime.Output 同义)
FMT = Opt('--format', dest='fmt', short=('-f',),
          help='输出格式: text / markdown / json')
OUT = Opt('--output', short=('-o',), help='写入文件; 给目录则按时间命名')


def family_opts(name: str) -> tuple[Opt, ...]:
    """口径型命令的标准三件套: --kind / --list / --arg

    三者总是一起出现, 且帮助文案里要带命令名, 所以按命令生成而不能共用常量。
    """
    return (
        Opt('--kind', help=f'扩展口径 (先跑 prism {name} --list)'),
        Opt('--list', dest='list_kinds', type=bool, default=False,
            help=f'列出 {name} 的扩展口径'),
        Opt('--arg', type=str, default=None, multiple=True, metavar='K=V',
            help='额外参数 K=V, 可重复'),
    )
