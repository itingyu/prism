"""stock 子命令入口 do_stock (拆包: __init__ + _common/_textfmt/_render/_actions*)"""
"""prism 动作: 动作分发 + 输出渲染

两座桥 (bridge/engine.py 脚本层 / bridge/srv.py 编排层) 在这里汇合成一个扁平的动作表。动作分三类:

    数据动作  quote pool check calendar flow news announcement financials
              analyze screen risk            —— 走 engine 脚本层
    透传动作  mcp <tool>                     —— 按名调用 24 个动作 (未单独暴露的那些)
    元动作   tools health                    —— 能力清单与两侧探活

输出与 prism 其他数据命令一致: 数据动作按 args.format 自己渲染 (json 全字段 /
text 行内可读 / markdown 表格), 走 cli.app._run 的 emit 落盘通道。

口径纪律 (从 stock-master 继承, 现由 engine 维护):
  - 接口返回 0/空 不当正常值, 由各桥透传 status, 渲染时显式标注
  - 北向资金不可用必须显式 ⚠, 不填 0
  - 池/榜单类结果必带数据日 (date), 涨停池尤其 —— 接口对无效日期会静默回旧数据
"""
import sys

from prism.stock.bridge import ak as _ak
from prism.stock.bridge import http as _http
from prism.stock.error import StockError as _StockError
from prism.stock.bridge import eco as _eco
from prism.stock.bridge import engine as _engine
from prism.stock.bridge import rawapi as _raw
from prism.stock.bridge import srv as _srv


from prism.stock.command._registry import ACTIONS
from prism.stock.command._registry import USAGE
from prism.stock.command._render import _render

def do_stock(args, cfg):
    """分发 + 渲染。返回退出码: 0 成功 / 1 动作失败 / 2 用法错"""
    action = args.action
    if not action:
        print(USAGE, file=sys.stderr)
        return 2
    fn = ACTIONS.get(action)
    if not fn:
        print(f'unknown action: {action}\n\n{USAGE}', file=sys.stderr)
        return 2

    try:
        codes = getattr(args, 'codes', None)
        from prism.stock.name_index import NO_CODE_ACTIONS
        if codes and action not in NO_CODE_ACTIONS:
            from prism.stock.name_index import (MARKET_ACTIONS, guard_a_share,
                                                normalize_market, resolve_tokens)
            toks = list(codes)
            market = getattr(args, 'market', None)
            if market:
                # hk-quote / us-kline 等: 命令已定市场, 只校验归属, 不猜不换
                toks = guard_a_share(toks, action, market=market)
            elif action in MARKET_ACTIONS:
                toks = resolve_tokens(normalize_market(toks, action))
            else:
                toks = resolve_tokens(guard_a_share(toks, action))
            args.codes = toks
        out = fn(args, cfg)
    except ImportError as e:
        # requests 是 stock/http.py 的顶层 import, 而 stock 整体是延迟导入
        # —— 少装一个包的表现是 `prism` 抛一串 importlib 栈, 而
        # search/fetch 等其他命令完全正常, 很难联想到是依赖缺失。
        from prism.core import deps
        print(f'error: stock 不可用 — {deps.install_hint(e.name or "")}',
              file=sys.stderr)
        return 2
    except _engine.EngineMissing as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    except _srv.SrvError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    except _raw.RawApiError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    except _eco.EcoError as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
    except _ak.AkUnavailable as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    except _ak.AkFailed as e:
        # 上游真的没有当日数据 (非交易日/该股没上榜) 与"接口坏了"要分开说
        print(f'error: {e}', file=sys.stderr)
        return 1
    except _http.HttpError as e:
        print(f'http error: {e}', file=sys.stderr)
        return 3
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    except _StockError as e:
        # 各通道异常已按类型接住; 这里兜 StockError 基类 (退出码由类声明)
        print(f'error: {e}', file=sys.stderr)
        return e.exit_code
    except Exception as e:  # noqa: BLE001
        # 第三方库 (requests-shim / curl_cffi) 的网络异常不该以堆栈示人
        import os
        if os.environ.get('PRISM_DEBUG'):
            raise
        print(f'error: {type(e).__name__}: {e}', file=sys.stderr)
        return 1

    # 载荷形状问题在渲染层拦 (raw HTML / 字符串化 data), 不让噪声进结果
    _render(out, args.format, action)
    return 0

