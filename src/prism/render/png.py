"""SVG → PNG 栅格化 (可选能力, 不是硬依赖)

SVG 是本仓的主输出: 纯文本、不用装包、缩放不糊。但贴到微信/钉钉/PPT 里
PNG 更省事, 所以给一条转换通道, 按可用性降级:

    rsvg-convert (librsvg, 有 CJK 字体时中文正常)
        ↓ 没有
    cairosvg (纯 pip 包, 一样依赖系统字体)
        ↓ 没有
    明确报错, 让调用方继续用 SVG —— 不静默退回一张白图

字体不走 SVG 内嵌: 内嵌要读 TTF 并转 base64, 体积翻几倍; 本机有
Noto Sans CJK 就够, 没有字体时中文变豆腐块, 这一点在 _warn_no_cjk 里提示。
"""
import shutil
import subprocess
import sys

CJK_HINTS = ('Noto Sans CJK', 'Source Han', 'WenQuanYi', 'PingFang',
             'Microsoft YaHei', 'SimHei')


_CJK_CACHE = None
_CJK_WARNED = []            # 缺字体提示只说一次


def _has_cjk():
    """fontconfig 里有没有中文字体 (没有就只警告, 不拦转换)

    结果缓存: fc-list 是一次进程调用 (沙盒里没装 fontconfig 时还要等满
    超时), 而一次运行可能转多张图 —— 进程内字体列表不会变, 查一次就够。
    """
    global _CJK_CACHE
    if _CJK_CACHE is not None:
        return _CJK_CACHE
    if not shutil.which('fc-list'):
        _CJK_CACHE = True
        return _CJK_CACHE
    try:
        out = subprocess.run(['fc-list'], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        _CJK_CACHE = True
        return _CJK_CACHE
    _CJK_CACHE = any(h in out for h in CJK_HINTS)
    return _CJK_CACHE


def svg_to_png(svg_text, path, zoom=2.0):
    """栅格化到 path; 返回 path。zoom=2 相当于 2 倍 retina, 贴图更清晰"""
    data = svg_text.encode('utf-8')
    exe = shutil.which('rsvg-convert')
    if exe:
        cmd = [exe, '-z', str(zoom), '-b', 'white', '-o', path]
    else:
        try:
            import cairosvg  # noqa: F401
        except ImportError:
            raise RuntimeError(
                '没有可用的 SVG→PNG 转换器: 装 librsvg (rsvg-convert) 或 '
                'pip install cairosvg; 也可以直接输出 SVG (--chart-out x.svg)')
        cmd = None

    if not _has_cjk() and not _CJK_WARNED:
        # 缺字体是环境问题, 每张图都提一遍等于噪声; 一个进程提一次足够
        _CJK_WARNED.append(1)
        print('提示: 系统缺中文字体, PNG 里的中文可能变方框 (SVG 可正常显示)',
              file=sys.stderr)

    if cmd:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(f'rsvg-convert 失败: '
                               f'{p.stderr.decode("utf-8", "ignore")[:200]}')
    else:
        import cairosvg
        cairosvg.svg2png(bytestring=data, write_to=path, scale=zoom,
                         background_color='white')
    return path
