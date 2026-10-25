"""数据源聚合门面 —— 按源拆包, 对外仍是同一个 `APIClient`

`APIClient` 只是把各源 mixin 合到一个类上, 所以:
  - 方法清单按源分组见 `prism lookup --by site` (现 161 个)
  - session 只有一份 (`SourceBase.__init__`), token 与 cookie 缓存共享
  - 新增一个源 = 加一个 `sources/<源>.py`, 这里加一行 mixin, 别处不动

## 源清单

| 模块 | 源 | 方法数 |
|---|---|---|
| `ths.py` | 同花顺 (v cookie 反爬) | 35 |
| `em.py` | 东方财富 (ut token) | 34 |
| `xueqiu.py` | 雪球 (TLS 指纹) | 31 |
| `sina.py` | 新浪财经 + 腾讯行情 CDN (gtimg) | 29 |
| `tencent.py` | 腾讯财经 | 9 |
| `cninfo.py` | 巨潮资讯 | 6 |
| `csindex.py` | 中证指数 | 4 |
| `sse.py` | 上交所 | 3 |
| `np.py` | 东财公告老域 | 2 |
| `ef.py` | efinance (本地库) | 3 |

## 传输层为什么留在公共底座

`_xueqiu_session` 名义属雪球, 实际 `tencent_kline_global` / `tencent_us_kline`
/ `tencent_minute` 也借它 —— 要 curl_cffi 指纹才能过 `web.ifzq.gtimg.cn`,
但请求打的是腾讯域名。属传输层而非数据源, 故在 `_base.py`。
"""
from prism.stock.bridge.sources._base import SourceBase, _err, _ok
from prism.stock.bridge.sources.ths import ThsSource
from prism.stock.bridge.sources.em import EmSource
from prism.stock.bridge.sources.xueqiu import XueqiuSource
from prism.stock.bridge.sources.sina import SinaSource
from prism.stock.bridge.sources.tencent import TencentSource
from prism.stock.bridge.sources.cninfo import CninfoSource
from prism.stock.bridge.sources.csindex import CsindexSource
from prism.stock.bridge.sources.sse import SseSource
from prism.stock.bridge.sources.np import NpSource
from prism.stock.bridge.sources.ef import EfSource
from prism.stock.bridge.sources.naver import NaverSource

# ── 源注册表: 工厂的单一事实来源 ─────────────────────────────────
# 新增一个源 = 1) 加 sources/<源>.py 2) 在 APIClient mixin 加一行
# 3) 在这里登记。`prism lookup --by site` 的分组、selftest 的源
# 清单未来都从这里取, 不再各自维护一份名单 (名单漂移 = 测的不是线上)。
SOURCES = {
    'ths': ThsSource, 'em': EmSource, 'xueqiu': XueqiuSource,
    'sina': SinaSource, 'tencent': TencentSource, 'cninfo': CninfoSource,
    'csindex': CsindexSource, 'sse': SseSource, 'np': NpSource,
    'ef': EfSource, 'naver': NaverSource,
}

def source_class(name):
    """按名字取源类; 未知名字抛错并列出可用项 (不静默返回 None)"""
    try:
        return SOURCES[name]
    except KeyError:
        raise KeyError(f'未知数据源: {name}; 可用: {", ".join(sorted(SOURCES))}')


class APIClient(ThsSource, EmSource, XueqiuSource, SinaSource, TencentSource,
                CninfoSource, CsindexSource, SseSource, NpSource, EfSource,
                NaverSource):
    """十一个数据源的聚合客户端。

    MRO 上各源互不重叠 (方法名前缀即归属), 只有 session 状态来自
    `SourceBase.__init__` —— 三份持 token/session 的模块 (rawapi / 服务端 /
    stock-master) 拿到的仍是同一个类、同一份缓存。
    """
# 源 → mixin, 供 tools/ 与文档查询用, 也让新增源只需改这一处
SOURCES = {
    'ths': ThsSource, 'em': EmSource, 'xueqiu': XueqiuSource, 'sina': SinaSource,
    'tencent': TencentSource, 'cninfo': CninfoSource, 'csindex': CsindexSource,
    'sse': SseSource, 'np': NpSource, 'ef': EfSource, 'naver': NaverSource,
}

__all__ = ['APIClient', 'SourceBase', 'SOURCES', '_ok', '_err']