"""prism pydata: 外部金融库任意函数, 走 prism 传输层出网

akshare / efinance / adata / qstock 这些库 99% 是裸 requests 出网, 站点一收紧
反爬就 RemoteDisconnected。这里把 `requests.Session.request` 整个换成 prism
的指纹通道再调库, 业务代码零改动。
"""
import json as _json
import sys

import typer

from prism.cli.runtime import Fmt, Output, _CTX, _run

USAGE = ('用法: prism pydata 库.函数 实参JSON  (akshare/efinance/adata/qstock '
         '装哪个用哪个);  例: prism pydata akshare.stock_zh_a_hist '
         "'{\"symbol\":\"600519\",\"period\":\"daily\"}'")


def pydata_cmd(qual: str = typer.Argument(None,
                                          help='外部库函数全限定名: akshare.stock_zh_a_hist '
                                               '/ efinance.stock.get_quote_history / 深路径也行'),
               payload: str = typer.Argument(None,
                                             help='实参: JSON dict → kwargs / JSON list → '
                                                  '位置参数 / 其他 → 单个位置参数'),
               lib: str = typer.Option('akshare', '--lib',
                                       help='qual 不带包名时用这个补全: akshare/efinance/adata/qstock...'),
               timeout: int = typer.Option(15, '--timeout', help='单请求超时秒'),
               pace_ms: int = typer.Option(120, '--pace-ms',
                                           help='相邻请求最小间隔 (防突发限流), 0=关'),
               rows: int = typer.Option(30, '-n', '--limit',
                                        help='text 模式下最多打印多少行 (json 全量)'),
               fmt: str = Fmt, output: str = Output):
    """外部金融库任意函数, 走 prism 传输层出网 (chrome 指纹/代理路由/限流重试)"""
    a = _CTX['args']
    a.no_cache = True
    as_csv = str(fmt or '').strip().lower() == 'csv'

    def fn(args, cfg):
        from prism.net.pyshim import call_py
        if not qual:
            print(USAGE)
            return 2
        pay = payload
        if pay in (None, '-'):
            pay = sys.stdin.read() if not sys.stdin.isatty() else None
        if pay:
            try:
                parsed = _json.loads(pay) if pay[:1] in ('{', '[') else pay
            except ValueError:
                parsed = pay
        else:
            parsed = None
        try:
            res = call_py(qual, parsed, lib=lib, timeout=timeout, pace_ms=pace_ms)
        except Exception as e:                        # noqa: BLE001
            print(f'✗ {type(e).__name__}: {e}')
            return 1
        f = args.format
        if f == 'json':
            print(_json.dumps(res, ensure_ascii=False))
            return 0
        if res['kind'] == 'dataframe':
            import pandas as _pd
            df = _pd.DataFrame(res['rows'], columns=res['columns'])
            if as_csv:
                print(df.head(rows).to_csv(index=False), end='')
            elif f == 'markdown':
                print(df.head(rows).to_markdown(index=False))
            else:
                print(f'{res["module"]}.{res["func"]}  {res["n"]} 行  '
                      f'{res["elapsed_s"]}s  (经 prism 指纹通道)')
                print(df.head(rows).to_string(index=False, max_colwidth=28))
                if res['n'] > rows:
                    print(f'… 共 {res["n"]} 行, -f json 出全量')
        else:
            print(_json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    return _run('pydata', fn, 'text' if as_csv else fmt, output)
