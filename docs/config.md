# 配置与本地状态

## `~/.prism/` 里有什么

| 路径 | 作用 |
|---|---|
| `config.json` | 用户配置（见下）。`prism config list` 看全部键 |
| `rules.json` | 出网路由规则：哪些域名直连、哪些走代理 |
| `state.json` | 跨进程持久状态（限流配额、站点冷却） |
| `name_map.json` | 代码 ↔ 名称索引，7 天过期 |
| `xueqiu_cookies.json` | 雪球会话（首次访问后落盘复用） |
| `cache/` | 响应缓存，按桶分 TTL |
| `positions.json` | 持仓台账（`prism position`） |
| `geo/` | GeoIP / GeoSite 库（首次运行从包内释放，可单独更新） |

目录位置由 `PRISM_DIR` 覆盖，默认 `~/.prism`。整个目录可以随时删 —— 删掉只是丢缓存
和持仓台账，不会损坏安装。

## `prism config`

```bash
prism config list              # 全部键，* 标出显式设置过的
prism config get timeout
prism config set timeout 30    # 当场校验，非法值直接拒
prism config unset timeout     # 回到默认
```

键表与校验集中在 `core/config_schema.py`，`config set` 只写入用户文件里实际有的键，
不会把默认值整份落盘 —— 否则以后调默认值会被旧配置文件盖住。

## 常用键

| 键 | 默认 | 说明 |
|---|---|---|
| `timeout` | 15 | 单请求超时秒数 |
| `retries` | 0 | 失败重试次数（仅幂等 GET/HEAD） |
| `proxy_fallback` | on | 代理连不上时改走直连 |
| `proxy_dns_ttl` | 300 | 代理侧 DNS 缓存秒数 |
| `cache` | 未设 | 缓存开关 |
| `cache_dir` | `~/.prism/cache` | 缓存目录 |
| `cache_ttl` | `{}` | 分桶 TTL 覆盖，如 `cache_ttl.search=30` |
| `rules_file` | 未设 | 换一份路由规则文件 |
| `ssl_verify` | **off** | 证书校验总开关 |
| `ca_bundle` | 未设 | 自定义 CA 包，`ssl_verify=on` 时替代系统 CA |
| `verify_hosts` | `[]` | 单独关掉校验的域名（自签 / 过期证书站） |

`config list` 里还会看到 `crawl_dir` / `extract` / `market` 等键 —— 它们属于同源的
net 层，股票取数用不到，留着不影响的就留着。

## 证书校验

默认 `ssl_verify=off`，即**不校验证书**。这是有意的取舍：新装环境（精简容器、
Android、公司网络 MITM）最常见的处境就是证书链还没备好，默认严格会让首次使用
直接不可用。

要严格就在配置里写 `on`：

```bash
prism config set ssl_verify on
```

此时 CA 的探测顺序是 `环境变量 → 系统路径 → certifi → 包内 data/certs/ca-bundle.pem`，
包内那份是兜底，平时轮不到。个别站点证书有问题时，用 `verify_hosts` 只放开那一个
域名，不要为了一站关掉全局。

## 路由

出网走哪条线路由 `~/.prism/rules.json` 判定，默认规则是「境内域名与 IP 直连，
其余走 `proxy:default`」。代理地址本身也在 `config.json` 里，密码是密文。

`http_proxy` / `https_proxy` 环境变量**故意不读** —— 容器里这类变量经常是全局预设的
噪声，跟着它走会让"直连"的主机实际绕进代理。要改线路只有两个地方：`rules.json`
和 `config.json`。

## 环境变量

| 变量 | 作用 |
|---|---|
| `PRISM_DIR` | 覆盖 `~/.prism` |
| `PRISM_DEBUG` | 异常打完整堆栈（默认只打一行原因） |
| `PRISM_LOG_FILE` | 日志落文件（等效 `--log-file`） |
| `PRISM_PLUGIN_DIR` | 插件目录 |
| `PRISM_NO_PATCH_REQUESTS` | 不接管 `requests.Session`（调试用） |

## 日志

诊断信息一律走 `prism` logger，**终端默认不打印**：正常路径没有 WARNING 以上日志，
降级（代理连不上改直连、缺中文字体、首次拉代码表）都记在 DEBUG。

但**日志默认落盘**——不打屏不等于没记录，网络降级这类问题复现不了，事后得能翻：

| 落盘 | 位置 |
|---|---|
| 默认 | `~/.prism/logs/prism.log`（DEBUG 全量，按天滚动） |
| 轮转 | 零点切分，旧档改名 `prism.log.YYYYMMDD`，保留 7 天（`LOG_KEEP_DAYS`） |
| 进程启动时 | 若发现文件是昨天以前的，先改名再开新档（prism 每次都是短命进程，只靠 handler 轮转会无限增长） |
| 关闭 | `PRISM_LOG=0` |
| 换路径 | `--log-file <路径>` 或 `PRISM_LOG_FILE=<路径>` |

终端：

| 用法 | 效果 |
|---|---|
| 默认 | 安静（只到 WARNING，正常跑 0 行） |
| `prism -d <命令>` | DEBUG 到 stderr（`-dd` 连三方库 urllib3/curl_cffi） |
| `PRISM_DEBUG=1` | 同上，免加参数 |

管道 / agent 场景下 stderr 应为空；出现 `[INFO]`、`W` 前缀都算回归。
