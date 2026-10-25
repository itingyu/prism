"""prism 的最小 CLI 运行时

只为 stock 命令服务: 复用 prism 的网络层/配置读取 (prism.net.*),
但不依赖 prism.cli —— prism 是独立仓库, CLI 生命周期自己管。
"""
import io
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime
from types import SimpleNamespace

import typer
from prism.net.proxy.store import load_config

from prism.stock.command import do_stock

_CTX = {'args': SimpleNamespace()}

Fmt = typer.Option(None, '-f', '--format',
                   help='输出格式: text / markdown / json')
Output = typer.Option(None, '-o', '--output',
                      help='写入文件; 给目录则按时间命名')

_EXT = {'json': '.json', 'markdown': '.md', 'text': '.txt'}
_FORMATS = ('json', 'text', 'markdown')


def _norm_fmt(fmt, default='text'):
    """-f 的别名收口成三种; 非法值当场报错, 别把脏格式传下去"""
    if not fmt:
        return default
    f = str(fmt).strip().lower()
    f = {'md': 'markdown', 'table': 'text'}.get(f, f)
    if f not in _FORMATS:
        raise ValueError(f'未知输出格式: {fmt} (可用: text / markdown / json)')
    return f


def _entry_fn(name):
    if name != 'stock':
        raise KeyError(name)
    return do_stock


def _emit_file(text, fmt, output, cmd='stock'):
    path = os.path.expanduser(output)
    if path.endswith(os.sep) or os.path.isdir(path):
        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
        path = os.path.join(path, f'prism-{cmd}-{ts}{_EXT.get(fmt, ".txt")}')
    else:
        root, ext = os.path.splitext(path)
        if not ext:
            path = root + _EXT.get(fmt, '.txt')
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
        if text and not text.endswith('\n'):
            f.write('\n')
    print(f'saved: {path} ({os.path.getsize(path)} bytes, format={fmt})',
          file=sys.stderr)


def _run(_name, fn, fmt, output, no_cache=False, no_proxy=False, cmd='stock'):
    cfg = load_config()
    args = _CTX['args']
    args.format = _norm_fmt(fmt or _CTX.get('stock_fmt'),
                            cfg.get('default_format') or 'text')
    args.output = output or _CTX.get('stock_output')
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(args, cfg)
    out = buf.getvalue()
    # 动作自己写了文件 (excel 出 xlsx) 就不再往同一路径写一份文本
    written = _CTX.pop('file_written', None)
    if written:
        print(f'saved: {written}', file=sys.stderr)
    elif args.output and args.output != '-':
        _emit_file(out, args.format, args.output, cmd=cmd)
    elif out:
        sys.stdout.write(out if out.endswith('\n') else out + '\n')
    rc = rc if rc not in (0, None) else 0
    # typer 不认函数返回值, 退出码必须显式抛出, 否则脚本里永远看到 0
    if rc:
        raise typer.Exit(code=rc)
    return 0
