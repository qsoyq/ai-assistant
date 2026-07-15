# `ai-assistant`

**Usage**:

```console
$ ai-assistant [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-v, -V, --version`
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `adb`: 管理 adb server。
* `agent-bark-notify`: Send Bark notifications from agent lifecycle hooks.
* `aliyun-oss`: 阿里云 OSS 工具集
* `bump-version`: 对当前目录的 pyproject.toml 的 project.version 加一。
* `cf-tunnel-watcher`: 监听 Cloudflare Tunnel 连接状态变化并执行命令
* `cloudflare-dns`: 管理 Cloudflare DNS 记录, 支持添加/修改 A 和 CNAME 记录
* `cookies`: 从本地浏览器中提取指定域名的 Cookie。
* `cursor-usage`: Get usage of Cursor.
* `disable-ssl-verify`: 聚合命令：同时管理 httpx 和 requests 的 SSL verify 禁用补丁。
* `docker`: Docker 相关工具
* `docker-hub-runner`: 监听 Docker Hub 镜像最新推送并执行命令
* `file-change-runner`: 监听文件变化并执行命令
* `freshrss`: FreshRSS 工具集.
* `ghi`: A Wrapper for github cli (https://cli.github.com/).
* `git-download`: 从 GitHub 仓库的某个分支下载单个文件或目录到本地路径。
* `greader`: Google Reader API 客户端工具
* `handoff`: macOS Handoff 操作工具
* `httpx-disable-verify`: 通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 httpx 的 SSL verify。
* `httpx-rfc-cache`: 通过 site-packages 下的 .pth 文件，为指定 Python 解释器全局启用 httpx 的 RFC 9111 HTTP cache。
* `lan-ddns`: 根据局域网设备的 MAC 地址定位其 IP, 并更新 Cloudflare 上的 A 记录 (DDNS)
* `mcd`: 基于 OpenAI Responses API 的 mcp-mcd 工具
* `mcp-cli`: MCP Client
* `opml`: Fetch RSS feeds from OPML file periodically.
* `plugins`: Manage ai-assistant companion plugins.
* `pypi-mirror`: 按 PEP 503 simple 索引镜像下载 (asyncio 驱动): 拉取索引页 -&gt; 并发抓取所有文件清单 -&gt;
* `pypi-upload`: 把本地的 whl / tar.gz 上传到指定仓库 (asyncio 并发, 直接调用 twine 库内 API)。
* `reality`: 基于 Xray REALITY 协议生成服务端与客户端配置, 可选自动安装 xray 并启用 systemd 服务。
* `realm`: 生成、查看、校验、安装 realm (https://github.com/zhboner/realm) TCP/UDP 中继。
* `requests-disable-verify`: 通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 requests 的 SSL verify。
* `route`: 跨平台运行时路由管理工具。
* `similar-questions`: Generate N similar questions by input query.
* `ssl`: 生成和管理 SSL 证书
* `stash-log`: Stash 抓包日志解析工具
* `tg-bot-click`: Telegram bot 自动点击工具。
* `udp`: UDP 端口可达性验证工具
* `uv-tool`: 管理通过 `uv tool` 安装的 CLI 工具。
* `win-env`: 查看/添加/修改 Windows 环境变量, 直接读写注册表 (HKCU / HKLM)。

## `ai-assistant adb`

**Usage**:

```console
$ ai-assistant adb [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `restart-all`: 强制重启 adb server, 以 -a 模式监听 0.0.0.0:&lt;port&gt;。

### `ai-assistant adb restart-all`

强制重启 adb server, 以 -a 模式监听 0.0.0.0:&lt;port&gt;。

**Usage**:

```console
$ ai-assistant adb restart-all [OPTIONS]
```

**Options**:

* `-P, --port INTEGER`: adb server 端口 (探测 + 启动均使用)  [default: 5037]
* `-t, --timeout FLOAT`: adb devices 探活超时 (秒)  [default: 5.0]
* `-f, --force`: 无视当前状态强制重启
* `-v, --verbose`: 打印 adb 详细输出
* `--help`: Show this message and exit.

## `ai-assistant agent-bark-notify`

**Usage**:

```console
$ ai-assistant agent-bark-notify [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `install`: Install agent-bark-notify plugins for...
* `hook`: Read hook JSON from stdin and send a...

### `ai-assistant agent-bark-notify install`

Install agent-bark-notify plugins for locally available agents.

This command checks for codex, claude, and openclaw CLIs in PATH.
When a CLI is present, it installs the matching agent-bark-notify plugin
with user/global scope. Missing CLIs are skipped.

Installed plugins:
  Codex:        agent-bark-notify-codex@ai-assistant
  Claude Code:  agent-bark-notify@ai-assistant --scope user
  OpenClaw:     local linked plugin from plugins/agent-bark-notify-openclaw

After installation, set BARK_DEVICE_KEY where hook commands can read it.
Optional env vars include BARK_SERVER, BARK_GROUP,
AGENT_BARK_NOTIFY_GROUP_MODE, AGENT_BARK_NOTIFY_HOOK_URL,
AGENT_BARK_NOTIFY_AUDIT_LOG, and AGENT_BARK_NOTIFY_AUDIT_LOG_FILE.

Codex and OpenClaw may run hooks in a restricted or service environment;
set env vars in the environment inherited by those hook processes.

**Usage**:

```console
$ ai-assistant agent-bark-notify install [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `ai-assistant agent-bark-notify hook`

Read hook JSON from stdin and send a best-effort Bark notification.

**Usage**:

```console
$ ai-assistant agent-bark-notify hook [OPTIONS]
```

**Options**:

* `--runtime [auto|codex|claude|openclaw]`: Hook runtime: codex, claude, openclaw, or auto.  [default: auto]
* `--event [auto|completion|approval_needed|failed]`: Notification event override.  [default: auto]
* `--message TEXT`: Override short notification body.
* `--group-mode [agent|project|project-branch]`: Bark group mode: agent, project, or project-branch.
* `--summary-mode [fixed|extract]`: Notification summary mode: fixed or extract.  [default: fixed]
* `--summary-max-chars INTEGER RANGE`: Maximum extractive summary length.  [default: 120; x&gt;=1]
* `--dry-run`: Print notification summary without sending Bark request.
* `--no-dedupe`: Disable duplicate suppression.
* `--help`: Show this message and exit.

## `ai-assistant aliyun-oss`

**Usage**:

```console
$ ai-assistant aliyun-oss [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `upload`: 上传单个文件到 OSS, 大文件自动分片续传.
* `download`: 从 OSS 下载单个文件, 大文件自动分片续传.
* `ls`: 列举 OSS 对象.
* `rm`: 删除 OSS 对象, 支持多个 key 或前缀递归.
* `stat`: 查看 OSS 对象元数据.
* `cat`: 打印 OSS 对象内容到 stdout (受 --max-size 限制).
* `sign`: 生成预签名 URL, 直接打印到 stdout.
* `sync`: 目录同步: 本地 ↔ OSS, 默认按 size +...

### `ai-assistant aliyun-oss upload`

上传单个文件到 OSS, 大文件自动分片续传.

**Usage**:

```console
$ ai-assistant aliyun-oss upload [OPTIONS] LOCAL_PATH OSS_KEY
```

**Arguments**:

* `LOCAL_PATH`: 本地文件路径  [required]
* `OSS_KEY`: OSS 对象 key  [required]

**Options**:

* `-f, --force`: 目标已存在时仍上传 (覆盖)
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss download`

从 OSS 下载单个文件, 大文件自动分片续传.

**Usage**:

```console
$ ai-assistant aliyun-oss download [OPTIONS] OSS_KEY LOCAL_PATH
```

**Arguments**:

* `OSS_KEY`: OSS 对象 key  [required]
* `LOCAL_PATH`: 本地保存路径  [required]

**Options**:

* `-f, --force`: 本地已存在时仍下载 (覆盖)
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss ls`

列举 OSS 对象.

**Usage**:

```console
$ ai-assistant aliyun-oss ls [OPTIONS] [PREFIX]
```

**Arguments**:

* `[PREFIX]`: 对象 key 前缀

**Options**:

* `-r, --recursive`: 递归列举所有层级
* `-n, --limit INTEGER`: 最多返回多少条, 0 表示无限  [default: 100]
* `-l, --long`: 显示大小、修改时间、存储类型
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss rm`

删除 OSS 对象, 支持多个 key 或前缀递归.

**Usage**:

```console
$ ai-assistant aliyun-oss rm [OPTIONS] KEYS...
```

**Arguments**:

* `KEYS...`: OSS 对象 key, 可多个  [required]

**Options**:

* `-y, --yes`: 跳过确认
* `-r, --recursive`: 按前缀递归删除
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss stat`

查看 OSS 对象元数据.

**Usage**:

```console
$ ai-assistant aliyun-oss stat [OPTIONS] OSS_KEY
```

**Arguments**:

* `OSS_KEY`: OSS 对象 key  [required]

**Options**:

* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss cat`

打印 OSS 对象内容到 stdout (受 --max-size 限制).

**Usage**:

```console
$ ai-assistant aliyun-oss cat [OPTIONS] OSS_KEY
```

**Arguments**:

* `OSS_KEY`: OSS 对象 key  [required]

**Options**:

* `--max-size INTEGER`: 允许打印的最大字节数, 防止误打印巨大文件  [default: 1048576]
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss sign`

生成预签名 URL, 直接打印到 stdout.

**Usage**:

```console
$ ai-assistant aliyun-oss sign [OPTIONS] OSS_KEY
```

**Arguments**:

* `OSS_KEY`: OSS 对象 key  [required]

**Options**:

* `-e, --expires INTEGER`: URL 有效期, 秒  [default: 3600]
* `-m, --method TEXT`: HTTP 方法 (GET / PUT)  [default: GET]
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

### `ai-assistant aliyun-oss sync`

目录同步: 本地 ↔ OSS, 默认按 size + x-oss-meta-mtime 比对.

OSS 端两种写法等价 (URI 内的 bucket 必须与 --bucket / OSS_BUCKET 一致):

  oss:&lt;prefix&gt;/             从 --bucket 读取 bucket
  oss://&lt;bucket&gt;/&lt;prefix&gt;/  s3 风格, bucket 写在 URI 里

使用示例:
  ai-assistant aliyun-oss sync ./dist/ oss:web/                  # 上传
  ai-assistant aliyun-oss sync ./dist/ oss://mybucket/web/       # 上传, 显式 bucket
  ai-assistant aliyun-oss sync oss:backup/ ./restore/            # 下载
  ai-assistant aliyun-oss sync ./dist/ oss:web/ --dry-run --max-files 50

**Usage**:

```console
$ ai-assistant aliyun-oss sync [OPTIONS] SRC DST
```

**Arguments**:

* `SRC`: 源路径, 本地路径或 oss:&lt;prefix&gt;/ 或 oss://&lt;bucket&gt;/&lt;prefix&gt;/  [required]
* `DST`: 目标路径, 本地路径或 oss:&lt;prefix&gt;/ 或 oss://&lt;bucket&gt;/&lt;prefix&gt;/  [required]

**Options**:

* `--delete`: 删除目标端不存在于源端的文件 (镜像同步)
* `--dry-run`: 只显示需要同步的文件列表, 不实际传输
* `--max-files INTEGER`: 本次最多同步多少个文件, 默认无限
* `--workers INTEGER`: 并发传输数  [default: 4]
* `-f, --force`: 忽略 size/mtime 比较, 全部覆盖
* `--access-key-id TEXT`: AccessKey ID  [env var: OSS_ACCESS_KEY_ID]
* `--access-key-secret TEXT`: AccessKey Secret  [env var: OSS_ACCESS_KEY_SECRET]
* `--endpoint TEXT`: OSS endpoint, 如 https://oss-cn-hangzhou.aliyuncs.com  [env var: OSS_ENDPOINT]
* `--region TEXT`: OSS 区域, 如 cn-hangzhou; 与 --endpoint 二选一  [env var: OSS_REGION]
* `--bucket TEXT`: Bucket 名称  [env var: OSS_BUCKET]
* `--security-token TEXT`: STS 临时凭证 Token, 可选  [env var: OSS_SESSION_TOKEN]
* `--help`: Show this message and exit.

## `ai-assistant bump-version`

**Usage**:

```console
$ ai-assistant bump-version [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant cf-tunnel-watcher`

**Usage**:

```console
$ ai-assistant cf-tunnel-watcher [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `watch`: 监听 Cloudflare Tunnel 连接状态变化并执行命令

### `ai-assistant cf-tunnel-watcher watch`

监听 Cloudflare Tunnel 连接状态变化并执行命令

对于连续的不健康状态, 也会重复执行命令, 直到状态变为健康。

通过轮询 cloudflared 的 metrics 端点 `/ready` 来检测隧道连接状态。
cloudflared 默认在 `127.0.0.1:20241` 暴露 metrics 服务，
可通过 `cloudflared --metrics` 参数自定义地址。

传递给执行命令子进程的环境变量:
- `CF_TUNNEL_METRICS_URL`: metrics 端点地址
- `CF_TUNNEL_STATUS`: 当前状态 (`ready`, `not_ready`, `unreachable`)
- `CF_TUNNEL_STATUS_CODE`: HTTP 状态码（不可达时为 `0`）
- `CF_TUNNEL_DETAIL`: 状态详情
- `CF_TUNNEL_IS_HEALTHY`: 是否健康 (`true` / `false`)

示例:
- 监听状态变化:
        ai-assistant cf-tunnel-watcher watch &#x27;echo &quot;status=$CF_TUNNEL_STATUS&quot;&#x27; --run-on-start
- 自定义 metrics 地址:
        ai-assistant cf-tunnel-watcher watch &#x27;echo &quot;$CF_TUNNEL_STATUS&quot;&#x27; -m http://127.0.0.1:12345
- 启动时立即执行:
        ai-assistant cf-tunnel-watcher watch &#x27;notify.sh&#x27; --run-on-start
- 仅在不健康时执行:
        ai-assistant cf-tunnel-watcher watch &#x27;alert.sh&#x27; --run-on-unhealthy
- 调整轮询间隔:
        ai-assistant cf-tunnel-watcher watch &#x27;your-command&#x27; --interval 10

**Usage**:

```console
$ ai-assistant cf-tunnel-watcher watch [OPTIONS] RUN_CMD
```

**Arguments**:

* `RUN_CMD`: 检测到状态变化后执行的 shell 命令  [required]

**Options**:

* `-m, --metrics-url TEXT`: cloudflared metrics 端点地址  [default: http://127.0.0.1:20241]
* `-i, --interval FLOAT RANGE`: 轮询间隔（秒）  [default: 10; x&gt;=1]
* `--request-timeout FLOAT RANGE`: 请求超时时间（秒）  [default: 5.0; x&gt;=1]
* `--run-on-start`: 启动时立即执行一次命令
* `--run-on-unhealthy`: 仅在状态变为不健康时执行命令（默认任何状态变化都执行）
* `-s, --sleep-after-run FLOAT RANGE`: 执行命令后等待时间（秒）  [default: 60; x&gt;=0]
* `--help`: Show this message and exit.

## `ai-assistant cloudflare-dns`

**Usage**:

```console
$ ai-assistant cloudflare-dns [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: 列出/筛选 Cloudflare DNS 记录
* `upsert`: 添加或修改 Cloudflare DNS 记录
* `a`: 添加或修改 Cloudflare A 记录
* `cname`: 添加或修改 Cloudflare CNAME 记录

### `ai-assistant cloudflare-dns list`

列出/筛选 Cloudflare DNS 记录

使用示例:
- 查询 A 记录:        `ai-assistant cloudflare-dns list -z example.com --type A`
- 按记录值查询:      `ai-assistant cloudflare-dns list -z example.com --type A -c 1.2.3.4`
- 删除筛选结果预览:  `ai-assistant cloudflare-dns list -z example.com --type CNAME --search old --delete --dry-run`
- 删除筛选结果:      `ai-assistant cloudflare-dns list -z example.com --name old.example.com --delete`

**Usage**:

```console
$ ai-assistant cloudflare-dns list [OPTIONS]
```

**Options**:

* `-T, --type [a|cname]`: 按记录类型筛选: A 或 CNAME
* `-n, --name TEXT`: 按记录名/FQDN 精确筛选
* `-c, --content TEXT`: 按记录值/内容精确筛选, 如 A 的 IP 或 CNAME 目标
* `-s, --search TEXT`: 在记录名或内容中做本地子串筛选
* `-t, --token TEXT`: Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN
* `-z, --zone TEXT`: Cloudflare zone 名, list 必须指定  [required]
* `--delete`: 删除筛选出来的记录
* `--dry-run`: 配合 --delete 时只打印将删除的记录, 不真正调用 API
* `--help`: Show this message and exit.

### `ai-assistant cloudflare-dns upsert`

添加或修改 Cloudflare DNS 记录

使用示例:
- A 记录:     `ai-assistant cloudflare-dns upsert --type A -n nas.example.com -c 1.2.3.4`
- CNAME 记录: `ai-assistant cloudflare-dns upsert --type CNAME -n www.example.com -c target.example.com`
- 指定 zone:  `ai-assistant cloudflare-dns upsert --type A -n nas.example.com -c 1.2.3.4 -z example.com`

**Usage**:

```console
$ ai-assistant cloudflare-dns upsert [OPTIONS]
```

**Options**:

* `-T, --type [a|cname]`: 记录类型: A 或 CNAME  [required]
* `-n, --name TEXT`: 记录名/FQDN, 如 nas.example.com  [required]
* `-c, --content TEXT`: 记录内容: A 为 IPv4 地址, CNAME 为目标域名  [required]
* `-t, --token TEXT`: Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN
* `-z, --zone TEXT`: Cloudflare zone 名, 缺省按记录名自动匹配
* `--ttl INTEGER`: DNS TTL, 1 表示 auto  [default: 1]
* `--proxied / --no-proxied`: 是否经 Cloudflare 代理 (橙云)  [default: no-proxied]
* `--dry-run`: 只打印将要执行的变更, 不真正调用 API
* `--help`: Show this message and exit.

### `ai-assistant cloudflare-dns a`

添加或修改 Cloudflare A 记录

使用示例:
- `ai-assistant cloudflare-dns a -n nas.example.com -i 1.2.3.4`
- `ai-assistant cloudflare-dns a -n nas.example.com -i 1.2.3.4 --proxied`

**Usage**:

```console
$ ai-assistant cloudflare-dns a [OPTIONS]
```

**Options**:

* `-n, --name TEXT`: A 记录名/FQDN, 如 nas.example.com  [required]
* `-i, --ip TEXT`: IPv4 地址  [required]
* `-t, --token TEXT`: Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN
* `-z, --zone TEXT`: Cloudflare zone 名, 缺省按记录名自动匹配
* `--ttl INTEGER`: DNS TTL, 1 表示 auto  [default: 1]
* `--proxied / --no-proxied`: 是否经 Cloudflare 代理 (橙云)  [default: no-proxied]
* `--dry-run`: 只打印将要执行的变更, 不真正调用 API
* `--help`: Show this message and exit.

### `ai-assistant cloudflare-dns cname`

添加或修改 Cloudflare CNAME 记录

使用示例:
- `ai-assistant cloudflare-dns cname -n www.example.com -c target.example.com`
- `ai-assistant cloudflare-dns cname -n www.example.com -c target.example.com --proxied`

**Usage**:

```console
$ ai-assistant cloudflare-dns cname [OPTIONS]
```

**Options**:

* `-n, --name TEXT`: CNAME 记录名/FQDN, 如 www.example.com  [required]
* `-c, --target TEXT`: CNAME 目标域名, 如 target.example.com  [required]
* `-t, --token TEXT`: Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN
* `-z, --zone TEXT`: Cloudflare zone 名, 缺省按记录名自动匹配
* `--ttl INTEGER`: DNS TTL, 1 表示 auto  [default: 1]
* `--proxied / --no-proxied`: 是否经 Cloudflare 代理 (橙云)  [default: no-proxied]
* `--dry-run`: 只打印将要执行的变更, 不真正调用 API
* `--help`: Show this message and exit.

## `ai-assistant cookies`

**Usage**:

```console
$ ai-assistant cookies [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get`: 从本地浏览器提取指定域名的 Cookie
* `twitter`: 从本地浏览器提取 Twitter/X 的 Cookie
* `cursor`: 从本地浏览器提取 Cursor 的 Cookie

### `ai-assistant cookies get`

从本地浏览器提取指定域名的 Cookie

Usage::

    # 提取 github.com 的所有 Cookie（默认 string 格式: a=b; c=d）
    $ ai-assistant cookies get github.com

    # 同时提取多个域名的 Cookie
    $ ai-assistant cookies get github.com api.github.com

    # 以 JSON 格式输出
    $ ai-assistant cookies get github.com -f json

    # 以 Python dict 格式输出
    $ ai-assistant cookies get github.com -f dict

    # 只提取指定字段
    $ ai-assistant cookies get github.com -F session_id -F user_id

**Usage**:

```console
$ ai-assistant cookies get [OPTIONS] DOMAINS...
```

**Arguments**:

* `DOMAINS...`: 目标域名，可指定多个，例如 example.com api.example.com  [required]

**Options**:

* `-f, --format [string|dict|json]`: 输出格式: string (a=b; c=d), dict (Python dict), json (JSON 字符串)  [default: string]
* `-F, --field TEXT`: 只提取指定名称的 Cookie，可多次使用
* `--help`: Show this message and exit.

### `ai-assistant cookies twitter`

从本地浏览器提取 Twitter/X 的 Cookie

Usage::

    # 提取所有 Twitter Cookie（默认 string 格式: a=b; c=d）
    $ ai-assistant cookies twitter

    # 以 JSON 格式输出
    $ ai-assistant cookies twitter -f json

    # 以 Python dict 格式输出
    $ ai-assistant cookies twitter -f dict

    # 只提取 auth_token 和 ct0
    $ ai-assistant cookies twitter -F auth_token -F ct0

**Usage**:

```console
$ ai-assistant cookies twitter [OPTIONS]
```

**Options**:

* `-f, --format [string|dict|json]`: 输出格式: string (a=b; c=d), dict (Python dict), json (JSON 字符串)  [default: string]
* `-F, --field TEXT`: 只提取指定名称的 Cookie，可多次使用
* `--help`: Show this message and exit.

### `ai-assistant cookies cursor`

从本地浏览器提取 Cursor 的 Cookie

Usage::

    # 提取所有 Cursor Cookie（默认 string 格式: a=b; c=d）
    $ ai-assistant cookies cursor

    # 以 JSON 格式输出
    $ ai-assistant cookies cursor -f json

    # 以 Python dict 格式输出
    $ ai-assistant cookies cursor -f dict

    # 只提取 WorkosCursorSessionToken
    $ ai-assistant cookies cursor -F WorkosCursorSessionToken

**Usage**:

```console
$ ai-assistant cookies cursor [OPTIONS]
```

**Options**:

* `-f, --format [string|dict|json]`: 输出格式: string (a=b; c=d), dict (Python dict), json (JSON 字符串)  [default: string]
* `-F, --field TEXT`: 只提取指定名称的 Cookie，可多次使用
* `--help`: Show this message and exit.

## `ai-assistant cursor-usage`

**Usage**:

```console
$ ai-assistant cursor-usage [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `get-usage`: Excel 结构: Date: Mar 2, 02:13 PM User:...

### `ai-assistant cursor-usage get-usage`

Excel 结构:
    Date: Mar 2, 02:13 PM
    User: abc@example.com
    Kind: On-Demand
    Model: claude-4.6-opus-high-thinking
    Total Tokens: Tokens
    Cost: 0.15

**Usage**:

```console
$ ai-assistant cursor-usage get-usage [OPTIONS] CSV_PATH
```

**Arguments**:

* `CSV_PATH`: CSV 文件路径  [required]

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant disable-ssl-verify`

**Usage**:

```console
$ ai-assistant disable-ssl-verify [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `install`: 同时安装 httpx 和 requests 的 .pth 补丁。
* `uninstall`: 同时移除 httpx 和 requests 的 .pth 补丁。
* `status`: 查看 httpx 和 requests 的 .pth 补丁安装状态。

### `ai-assistant disable-ssl-verify install`

同时安装 httpx 和 requests 的 .pth 补丁。

Usage examples::

    ai-assistant disable-ssl-verify install
    ai-assistant disable-ssl-verify install --yes
    ai-assistant disable-ssl-verify install --target ./custom-site-packages

**Usage**:

```console
$ ai-assistant disable-ssl-verify install [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 写入目录，默认使用 site.getsitepackages()[0]
* `-y, --yes`: 跳过确认提示直接写入
* `--help`: Show this message and exit.

### `ai-assistant disable-ssl-verify uninstall`

同时移除 httpx 和 requests 的 .pth 补丁。

Usage examples::

    ai-assistant disable-ssl-verify uninstall
    ai-assistant disable-ssl-verify uninstall --quiet

**Usage**:

```console
$ ai-assistant disable-ssl-verify uninstall [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `-q, --quiet`: 文件不存在时静默退出 0
* `--help`: Show this message and exit.

### `ai-assistant disable-ssl-verify status`

查看 httpx 和 requests 的 .pth 补丁安装状态。

Usage examples::

    ai-assistant disable-ssl-verify status

**Usage**:

```console
$ ai-assistant disable-ssl-verify status [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `--help`: Show this message and exit.

## `ai-assistant docker`

**Usage**:

```console
$ ai-assistant docker [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `log-clear`: 清空指定容器的日志
* `network-connect-all`: 将指定容器加入到全部普通 Docker 网络中

### `ai-assistant docker log-clear`

清空指定容器的日志

使用示例:
- `ai-assistant docker log-clear web`
- `ai-assistant docker log-clear 1234567890ab`
- `ai-assistant docker log-clear &#x27;*&#x27;`
- `ai-assistant docker log-clear web --helper-image alpine:3.20`

- 传入容器名称时，按精确名称匹配
- 传入容器 ID 时，支持完整 ID 或短 ID 精确匹配
- 传入 `*` 时，清空所有容器日志

优先直接清空 Docker 返回的 `LogPath`；
如果当前环境无法直接访问日志文件，会回退到临时辅助容器执行清理，
以兼容 Docker Desktop 等 daemon 文件系统不直接暴露给当前机器的场景。

`--helper-image` 需要包含可用的 shell，用于在辅助容器内截断日志文件。

**Usage**:

```console
$ ai-assistant docker log-clear [OPTIONS] CONTAINER
```

**Arguments**:

* `CONTAINER`: 精确容器名称、完整/短容器 ID，或 `*` 表示全部容器  [required]

**Options**:

* `--helper-image TEXT`: 无法直接访问日志文件时使用的辅助镜像  [default: alpine:3.20]
* `--help`: Show this message and exit.

### `ai-assistant docker network-connect-all`

将指定容器加入到全部普通 Docker 网络中

使用示例:
- `ai-assistant docker network-connect-all web`
- `ai-assistant docker network-connect-all 1234567890ab`

说明:
- 会遍历当前 Docker 上的全部网络
- 已连接的网络会自动跳过
- `host` 和 `none` 属于特殊网络，默认不处理

**Usage**:

```console
$ ai-assistant docker network-connect-all [OPTIONS] CONTAINER
```

**Arguments**:

* `CONTAINER`: 精确容器名称、完整容器 ID 或短容器 ID  [required]

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant docker-hub-runner`

**Usage**:

```console
$ ai-assistant docker-hub-runner [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `watch`: 监听 Docker Hub 镜像最新推送或指定 tag 的变化并执行命令

### `ai-assistant docker-hub-runner watch`

监听 Docker Hub 镜像最新推送或指定 tag 的变化并执行命令

传递给执行命令子进程的环境变量:
- `DOCKERHUB_IMAGE`: 镜像名，例如 `library/nginx`
- `DOCKERHUB_TAG`: 当前 tag，例如 `latest`
- `DOCKERHUB_IMAGE_WITH_TAG`: 带 tag 的镜像名，例如 `library/nginx:latest`
- `DOCKERHUB_DIGEST`: 当前镜像摘要，例如 `sha256:...`
- `DOCKERHUB_LAST_UPDATED`: Docker Hub 返回的最近更新时间

示例:
- 监听镜像最近推送:
        ai-assistant docker-hub-runner watch nginx &#x27;echo &quot;$DOCKERHUB_IMAGE_WITH_TAG&quot;&#x27;
- 监听镜像最近推送并立即执行:
        ai-assistant docker-hub-runner watch nginx &#x27;echo &quot;$DOCKERHUB_IMAGE_WITH_TAG&quot;&#x27; --run-on-start
- 只监听固定 tag:
        ai-assistant docker-hub-runner watch nginx &#x27;echo &quot;$DOCKERHUB_DIGEST&quot;&#x27; --tag latest
- 只监听固定 tag 并立即执行:
        ai-assistant docker-hub-runner watch nginx &#x27;echo &quot;$DOCKERHUB_DIGEST&quot;&#x27; --tag latest --run-on-start
- 调整轮询和请求超时:
        ai-assistant docker-hub-runner watch nginx &#x27;your-command&#x27; --interval 30 --request-timeout 5

**Usage**:

```console
$ ai-assistant docker-hub-runner watch [OPTIONS] IMAGE RUN_CMD
```

**Arguments**:

* `IMAGE`: Docker Hub 镜像名，如 `nginx` 或 `library/nginx`  [required]
* `RUN_CMD`: 检测到新镜像推送后执行的 shell 命令  [required]

**Options**:

* `--tag TEXT`: 固定监听某个 tag，例如 `latest`
* `-i, --interval FLOAT RANGE`: 轮询间隔（秒）  [default: 300; x&gt;=1]
* `--request-timeout FLOAT RANGE`: 请求 Docker Hub API 的超时时间（秒）  [default: 10.0; x&gt;=1]
* `--run-on-start`: 启动时立即执行一次命令
* `--help`: Show this message and exit.

## `ai-assistant file-change-runner`

**Usage**:

```console
$ ai-assistant file-change-runner [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `watch`: 监听文件变化并执行命令

### `ai-assistant file-change-runner watch`

监听文件变化并执行命令

Usage examples::

    # 监听单个文件变化后重启服务
    ai-assistant file-change-runner watch ./config.yaml &quot;systemctl restart myapp&quot;

    # 监听整个目录，启动时先执行一次
    ai-assistant file-change-runner watch ./src &quot;make build&quot; --run-on-start

    # 自定义轮询间隔和防抖时长
    ai-assistant file-change-runner watch ./data &quot;python process.py&quot; -i 1.0 -d 3.0

**Usage**:

```console
$ ai-assistant file-change-runner watch [OPTIONS] TARGET RUN_CMD
```

**Arguments**:

* `TARGET`: 监听目标（文件或目录）  [required]
* `RUN_CMD`: 检测到变化后执行的 shell 命令  [required]

**Options**:

* `-i, --interval FLOAT`: 事件轮询步长（秒）  [default: 0.2]
* `-d, --debounce FLOAT`: 两次触发的最短间隔（秒）  [default: 0.5]
* `--run-on-start`: 启动时先执行一次命令
* `--help`: Show this message and exit.

## `ai-assistant freshrss`

**Usage**:

```console
$ ai-assistant freshrss [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `subscribe`: 通过 FreshRSS 网页添加接口新增订阅源
* `refresh`: 刷新当前所有订阅源
* `cleanup-unread`: 按标题规则清理指定分类下的未读文章
* `cleanup-video-404`: 按 h5 video URL 404 状态清理指定分类下的未读文章
* `search`: 按标题或正文关键字搜索文章，可选标记命中结果为已读
* `disable-priority`: 将所有 feed 的 priority 置为 0

### `ai-assistant freshrss subscribe`

通过 FreshRSS 网页添加接口新增订阅源

会先读取添加页面，获取 CSRF token、分类，以及页面提供的订阅源类型选项，再提交表单。

常见 ``--feed-kind`` 参数映射::

    rss            -&gt; RSS / Atom (默认)
    atom           -&gt; RSS / Atom (默认)
    jsonfeed       -&gt; JSON 订阅源
    json           -&gt; JSON (点表达式)
    htmlxpath      -&gt; HTML + XPath (Web 抓取)
    xmlxpath       -&gt; XML + XPath
    htmlxpathjson  -&gt; HTML + XPath + JSON 点表示法（HTML 中的 JSON）
    25             -&gt; 直接使用 FreshRSS 表单值 25

Usage examples::
    FRESHRSS_ENDPOINT=https://rss.example.com/api/greader.php ai-assistant freshrss subscribe https://example.com/feed.json --category twitter --feed-kind jsonfeed
    ai-assistant freshrss subscribe https://example.com/feed.json --endpoint https://rss.example.com/api/greader.php --feed-kind 4 --cookies &quot;FreshRSS=...&quot;

**Usage**:

```console
$ ai-assistant freshrss subscribe [OPTIONS] FEED_URL
```

**Arguments**:

* `FEED_URL`: 订阅源地址  [required]

**Options**:

* `--endpoint TEXT`: FreshRSS 站点地址，例如 http://freshrss.docker.localhost/api/greader.php  [env var: FRESHRSS_ENDPOINT; required]
* `--category TEXT`: 分类名或分类 ID，留空则使用默认分类
* `--feed-kind TEXT`: 订阅源类型，如 jsonfeed、json、rss，或直接传 FreshRSS 的数值；仅当当前页面提供该字段时需要  [default: jsonfeed]
* `--cookies TEXT`: Cookie 字符串，格式如 &#x27;a=b; c=d&#x27;；为空时尝试从系统浏览器读取
* `--help`: Show this message and exit.

### `ai-assistant freshrss refresh`

刷新当前所有订阅源

通过 Google Reader API 获取订阅列表，然后逐个请求 stream/contents 触发服务端刷新。

Usage examples::
    ai-assistant freshrss refresh
    ai-assistant freshrss refresh http://freshrss.example.org/api/greader.php  --user &lt;user&gt; --token &lt;token&gt;

**Usage**:

```console
$ ai-assistant freshrss refresh [OPTIONS] ENDPOINT
```

**Arguments**:

* `ENDPOINT`: FreshRSS 端点地址  [env var: FRESHRSS_ENDPOINT; required]

**Options**:

* `--user TEXT`: FreshRSS 用户名  [env var: FRESHRSS_USER; required]
* `--token TEXT`: FreshRSS API Token  [env var: FRESHRSS_API_TOKEN; required]
* `--help`: Show this message and exit.

### `ai-assistant freshrss cleanup-unread`

按标题规则清理指定分类下的未读文章

读取指定分类中的所有未读文章；如果标题不包含任一 ``--keep`` 字符串，就将文章标记为已读。
Usage examples::
    ai-assistant freshrss cleanup-unread --category tech --keep AI --keep LLM --dry-run
    ai-assistant freshrss cleanup-unread --category tech --keep AI --keep LLM --limit 20
    ai-assistant freshrss cleanup-unread --category twitter --keep OpenAI --keep Anthropic

**Usage**:

```console
$ ai-assistant freshrss cleanup-unread [OPTIONS]
```

**Options**:

* `--category TEXT`: FreshRSS 分类名（不是分类 ID）  [required]
* `--keep TEXT`: 标题包含任一字符串时跳过，不标记为已读；可重复传入
* `--limit INTEGER RANGE`: 最多处理多少篇待标记为已读的文章；0 表示不限制  [default: 10; x&gt;=0]
* `--endpoint TEXT`: FreshRSS 端点地址  [env var: FRESHRSS_ENDPOINT; required]
* `--user TEXT`: FreshRSS 用户名  [env var: FRESHRSS_USER; required]
* `--token TEXT`: FreshRSS API Token  [env var: FRESHRSS_API_TOKEN; required]
* `--dry-run / --no-dry-run`: 只输出将被标记为已读的文章，不实际修改  [default: no-dry-run]
* `--ignore-case / --match-case`: 标题匹配时默认忽略大小写  [default: ignore-case]
* `--help`: Show this message and exit.

### `ai-assistant freshrss cleanup-video-404`

按 h5 video URL 404 状态清理指定分类下的未读文章

读取指定分类中的未读文章，先按标题关键字过滤，再提取正文 HTML 中 ``h5`` 元素下的
``video``/``source`` URL。只有当一篇文章的所有匹配视频 URL 都返回 HTTP 404 时，才会
将该文章标记为已读。``--dry-run`` 只预览待标记为已读的文章列表，不真实执行写入。

Usage examples::
    ai-assistant freshrss cleanup-video-404 --category videos --title &quot;Daily&quot; --dry-run
    ai-assistant freshrss cleanup-video-404 --label videos --title &quot;Daily&quot; --limit 20 --no-dry-run

**Usage**:

```console
$ ai-assistant freshrss cleanup-video-404 [OPTIONS]
```

**Options**:

* `--category, --label TEXT`: FreshRSS 分类/label 名称（不是分类 ID）  [required]
* `-t, --title TEXT`: 标题关键字；留空则检查分类下全部未读文章
* `--limit INTEGER RANGE`: 最多标记多少篇视频全部 404 的文章；0 表示不限制  [default: 10; x&gt;=0]
* `--endpoint TEXT`: FreshRSS 端点地址  [env var: FRESHRSS_ENDPOINT; required]
* `--user TEXT`: FreshRSS 用户名  [env var: FRESHRSS_USER; required]
* `--token TEXT`: FreshRSS API Token  [env var: FRESHRSS_API_TOKEN; required]
* `--dry-run / --no-dry-run`: 预览待标记为已读的视频 404 文章列表，不真实执行写入  [default: no-dry-run]
* `--ignore-case / --match-case`: 标题匹配时默认忽略大小写  [default: ignore-case]
* `--help`: Show this message and exit.

### `ai-assistant freshrss search`

按标题或正文关键字搜索文章，可选标记命中结果为已读

默认通过 FreshRSS API 拉取文章，支持按 ``--title`` 搜标题、按 ``--keyword`` 搜正文内容，
也支持通过 ``--category`` 限定分类。
当传入 ``--read`` 时，会将命中的文章标记为已读。

Usage examples::
    ai-assistant freshrss search --title OpenAI

**Usage**:

```console
$ ai-assistant freshrss search [OPTIONS]
```

**Options**:

* `-t, --title TEXT`: 标题关键字；留空则不按标题过滤
* `-k, --keyword TEXT`: 正文关键字；留空则不按正文过滤
* `--category TEXT`: 分类名；留空表示搜索全部分类
* `--limit INTEGER RANGE`: 最多显示并处理多少篇命中文章；0 表示不限制  [default: 10; x&gt;=0]
* `--read`: 是否将命中的文章标记为已读，默认不修改
* `--endpoint TEXT`: FreshRSS 端点地址  [env var: FRESHRSS_ENDPOINT; required]
* `--user TEXT`: FreshRSS 用户名  [env var: FRESHRSS_USER; required]
* `--token TEXT`: FreshRSS API Token  [env var: FRESHRSS_API_TOKEN; required]
* `--help`: Show this message and exit.

### `ai-assistant freshrss disable-priority`

将所有 feed 的 priority 置为 0

支持 SQLite 文件路径或数据库 DSN，适用于 sqlite/mysql/postgresql。

Usage examples::
    ai-assistant freshrss disable-priority /path/to/db.sqlite
    ai-assistant freshrss disable-priority sqlite:////path/to/db.sqlite
    ai-assistant freshrss disable-priority mysql://user:pass@127.0.0.1:3306/freshrss
    ai-assistant freshrss disable-priority postgresql://user:pass@127.0.0.1:5432/freshrss

**Usage**:

```console
$ ai-assistant freshrss disable-priority [OPTIONS] TARGET
```

**Arguments**:

* `TARGET`: SQLite 文件路径或数据库 DSN  [env var: FRESHRSS_DATABASE; required]

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant ghi`

**Usage**:

```console
$ ai-assistant ghi [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `release`: A Wrapper for github cli release command.

### `ai-assistant ghi release`

A Wrapper for github cli release command.

**Usage**:

```console
$ ai-assistant ghi release [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-v, -V, --version`
* `--help`: Show this message and exit.

**Commands**:

* `create`: Create a new GitHub Release for a repository.
* `delete`: Delete a release.

#### `ai-assistant ghi release create`

Create a new GitHub Release for a repository.

**Usage**:

```console
$ ai-assistant ghi release create [OPTIONS]
```

**Options**:

* `--tag TEXT`: Tag name, default to pyproject.toml version
* `-t, --title TEXT`: Release title
* `--target TEXT`: Target branch or full commit SHA (default: main branch)
* `-n, --notes TEXT`: Release notes
* `-p, --prerelease`: Mark the release as a prerelease
* `--verbose`
* `--help`: Show this message and exit.

#### `ai-assistant ghi release delete`

Delete a release.

**Usage**:

```console
$ ai-assistant ghi release delete [OPTIONS]
```

**Options**:

* `--tag TEXT`: Tag name, default to pyproject.toml version
* `--verbose`
* `-y, --yes`: Skip the confirmation prompt  [default: True]
* `--delete-tag / --no-delete-tag`: Also delete the local and remote git tag  [default: delete-tag]
* `--help`: Show this message and exit.

## `ai-assistant git-download`

**Usage**:

```console
$ ai-assistant git-download [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant greader`

**Usage**:

```console
$ ai-assistant greader [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `login`: 验证登录并显示用户信息
* `subscriptions`: 列出所有订阅源
* `tags`: 列出所有标签
* `unread-count`: 显示各订阅源的未读数量
* `stream-contents`: 获取指定 stream 的内容
* `stream-item-ids`: 获取指定 stream 的条目 ID 列表
* `edit-tag`: 修改条目的标签 (已读/加星等)
* `mark-all-read`: 将指定 stream 的所有条目标记为已读
* `subscription-edit`: 管理订阅 (订阅/退订/编辑)
* `fetch-unread`: 获取所有未读条目 (自动分页)
* `refresh-all`: 刷新所有订阅源

### `ai-assistant greader login`

验证登录并显示用户信息

Usage examples::
    ai-assistant greader login --endpoint https://rss.example.com/api/greader.php --user admin --password secret

**Usage**:

```console
$ ai-assistant greader login [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--help`: Show this message and exit.

### `ai-assistant greader subscriptions`

列出所有订阅源

Usage examples::
    ai-assistant greader subscriptions
    ai-assistant greader subscriptions --json

**Usage**:

```console
$ ai-assistant greader subscriptions [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--json`: 输出原始 JSON
* `--help`: Show this message and exit.

### `ai-assistant greader tags`

列出所有标签

Usage examples::
    ai-assistant greader tags

**Usage**:

```console
$ ai-assistant greader tags [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--help`: Show this message and exit.

### `ai-assistant greader unread-count`

显示各订阅源的未读数量

Usage examples::
    ai-assistant greader unread-count
    ai-assistant greader unread-count --json

**Usage**:

```console
$ ai-assistant greader unread-count [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--json`: 输出原始 JSON
* `--help`: Show this message and exit.

### `ai-assistant greader stream-contents`

获取指定 stream 的内容

stream 参数支持快捷名:
- ``reading-list`` -&gt; user/-/state/com.google/reading-list
- ``starred`` -&gt; user/-/state/com.google/starred
- ``read`` -&gt; user/-/state/com.google/read
- ``label/&lt;name&gt;`` -&gt; user/-/label/&lt;name&gt;
- 其他值直接作为 stream ID 使用

Usage examples::
    ai-assistant greader stream-contents reading-list -n 10
    ai-assistant greader stream-contents starred
    ai-assistant greader stream-contents label/tech -n 50
    ai-assistant greader stream-contents &#x27;feed/https://example.com/feed&#x27; -n 5

**Usage**:

```console
$ ai-assistant greader stream-contents [OPTIONS] STREAM
```

**Arguments**:

* `STREAM`: Stream ID 或快捷名 (reading-list, starred, read, label/&lt;name&gt;, feed/&lt;url&gt;)  [required]

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `-n, --count INTEGER`: 返回条目数  [default: 20]
* `--exclude TEXT`: 排除的 stream/tag ID
* `--continuation TEXT`: 分页 continuation token
* `--help`: Show this message and exit.

### `ai-assistant greader stream-item-ids`

获取指定 stream 的条目 ID 列表

Usage examples::
    ai-assistant greader stream-item-ids reading-list -n 100
    ai-assistant greader stream-item-ids starred

**Usage**:

```console
$ ai-assistant greader stream-item-ids [OPTIONS] STREAM
```

**Arguments**:

* `STREAM`: Stream ID 或快捷名  [required]

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `-n, --count INTEGER`: 返回条目数  [default: 1000]
* `--exclude TEXT`: 排除的 stream/tag ID
* `--include TEXT`: 包含的 stream/tag ID
* `--help`: Show this message and exit.

### `ai-assistant greader edit-tag`

修改条目的标签 (已读/加星等)

常用 tag:
- ``user/-/state/com.google/read`` -- 已读
- ``user/-/state/com.google/starred`` -- 加星
- ``user/-/state/com.google/kept-unread`` -- 保持未读

Usage examples::
    ai-assistant greader edit-tag ITEM_ID --add user/-/state/com.google/starred
    ai-assistant greader edit-tag ITEM_ID --remove user/-/state/com.google/read
    ai-assistant greader edit-tag ID1 ID2 ID3 --add user/-/state/com.google/read

**Usage**:

```console
$ ai-assistant greader edit-tag [OPTIONS] ITEM_IDS...
```

**Arguments**:

* `ITEM_IDS...`: 条目 ID，可传入多个  [required]

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `-a, --add TEXT`: 添加的 tag (如 user/-/state/com.google/starred)
* `-r, --remove TEXT`: 移除的 tag
* `--help`: Show this message and exit.

### `ai-assistant greader mark-all-read`

将指定 stream 的所有条目标记为已读

Usage examples::
    ai-assistant greader mark-all-read reading-list
    ai-assistant greader mark-all-read label/tech
    ai-assistant greader mark-all-read &#x27;feed/https://example.com/feed&#x27;

**Usage**:

```console
$ ai-assistant greader mark-all-read [OPTIONS] STREAM
```

**Arguments**:

* `STREAM`: Stream ID 或快捷名  [required]

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--timestamp INTEGER`: UNIX 时间戳起点，默认当前时间  [default: 0]
* `--help`: Show this message and exit.

### `ai-assistant greader subscription-edit`

管理订阅 (订阅/退订/编辑)

Usage examples::
    ai-assistant greader subscription-edit &#x27;feed/https://example.com/feed&#x27; --action subscribe --title &quot;Example&quot;
    ai-assistant greader subscription-edit &#x27;feed/https://example.com/feed&#x27; --action unsubscribe
    ai-assistant greader subscription-edit &#x27;feed/https://example.com/feed&#x27; --action edit --add-label tech

**Usage**:

```console
$ ai-assistant greader subscription-edit [OPTIONS] STREAM_ID
```

**Arguments**:

* `STREAM_ID`: 订阅 stream ID (如 feed/https://example.com/feed)  [required]

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `-a, --action TEXT`: 操作: subscribe, unsubscribe, edit  [required]
* `--title TEXT`: 订阅标题 (subscribe/edit 时可用)
* `--add-label TEXT`: 添加分类标签名
* `--remove-label TEXT`: 移除分类标签名
* `--help`: Show this message and exit.

### `ai-assistant greader fetch-unread`

获取所有未读条目 (自动分页)

自动处理 continuation 分页，获取指定 stream 下排除已读的全部条目。

Usage examples::
    ai-assistant greader fetch-unread
    ai-assistant greader fetch-unread --stream label/tech --limit 50
    ai-assistant greader fetch-unread --json

**Usage**:

```console
$ ai-assistant greader fetch-unread [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--stream TEXT`: Stream ID 或快捷名，默认 reading-list  [default: reading-list]
* `--limit INTEGER`: 最多返回条目数，0 表示不限制  [default: 0]
* `--json`: 输出原始 JSON
* `--help`: Show this message and exit.

### `ai-assistant greader refresh-all`

刷新所有订阅源

逐个请求每个订阅源的 stream/contents 以触发服务端拉取。

Usage examples::
    ai-assistant greader refresh-all

**Usage**:

```console
$ ai-assistant greader refresh-all [OPTIONS]
```

**Options**:

* `--endpoint TEXT`: GReader API 端点  [env var: GREADER_ENDPOINT; required]
* `--user TEXT`: 用户名  [env var: GREADER_USER; required]
* `--password TEXT`: 密码或 API Token  [env var: GREADER_PASSWORD; required]
* `--help`: Show this message and exit.

## `ai-assistant handoff`

**Usage**:

```console
$ ai-assistant handoff [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `website`: 点击 Dock 中的 Handoff 图标, 把 iPhone 当前网页接到 Mac

### `ai-assistant handoff website`

点击 Dock 中的 Handoff 图标, 把 iPhone 当前网页接到 Mac

使用示例:
- `ai-assistant handoff website`

前置条件:
- 系统设置 → 隐私与安全性 → 辅助功能 中授权运行此命令的终端
- iPhone 上对应 app 的网页处于活跃状态, 且 Mac Dock 中已出现 Handoff 图标

**Usage**:

```console
$ ai-assistant handoff website [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant httpx-disable-verify`

**Usage**:

```console
$ ai-assistant httpx-disable-verify [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `install`: 将 .pth 补丁安装到当前解释器的 site-packages。
* `uninstall`: 移除 site-packages 下的 .pth 补丁。
* `status`: 查看 .pth 补丁是否已安装及其内容。

### `ai-assistant httpx-disable-verify install`

将 .pth 补丁安装到当前解释器的 site-packages。

Usage examples::

    ai-assistant httpx-disable-verify install
    ai-assistant httpx-disable-verify install --yes
    ai-assistant httpx-disable-verify install --target ./custom-site-packages

**Usage**:

```console
$ ai-assistant httpx-disable-verify install [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 写入目录，默认使用 site.getsitepackages()[0]
* `-y, --yes`: 跳过确认提示直接写入
* `--help`: Show this message and exit.

### `ai-assistant httpx-disable-verify uninstall`

移除 site-packages 下的 .pth 补丁。

Usage examples::

    ai-assistant httpx-disable-verify uninstall
    ai-assistant httpx-disable-verify uninstall --quiet

**Usage**:

```console
$ ai-assistant httpx-disable-verify uninstall [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `-q, --quiet`: 文件不存在时静默退出 0
* `--help`: Show this message and exit.

### `ai-assistant httpx-disable-verify status`

查看 .pth 补丁是否已安装及其内容。

Usage examples::

    ai-assistant httpx-disable-verify status

**Usage**:

```console
$ ai-assistant httpx-disable-verify status [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `--help`: Show this message and exit.

## `ai-assistant httpx-rfc-cache`

**Usage**:

```console
$ ai-assistant httpx-rfc-cache [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `install`: 将 RFC HTTP cache .pth 补丁安装到目标解释器的...
* `uninstall`: 移除 site-packages 下的 RFC HTTP cache .pth 补丁。
* `status`: 查看 RFC HTTP cache .pth 补丁是否已安装及其内容。

### `ai-assistant httpx-rfc-cache install`

将 RFC HTTP cache .pth 补丁安装到目标解释器的 site-packages。

Usage examples::

    ai-assistant httpx-rfc-cache install
    ai-assistant httpx-rfc-cache install --python .venv/bin/python --yes
    ai-assistant httpx-rfc-cache install --target ./custom-site-packages --yes

**Usage**:

```console
$ ai-assistant httpx-rfc-cache install [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 写入目录；未指定时查询 --python 对应的 site-packages
* `-p, --python FILE`: 目标 Python 解释器路径，默认使用当前解释器
* `-y, --yes`: 跳过确认提示直接写入
* `--help`: Show this message and exit.

### `ai-assistant httpx-rfc-cache uninstall`

移除 site-packages 下的 RFC HTTP cache .pth 补丁。

Usage examples::

    ai-assistant httpx-rfc-cache uninstall
    ai-assistant httpx-rfc-cache uninstall --python .venv/bin/python --quiet

**Usage**:

```console
$ ai-assistant httpx-rfc-cache uninstall [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录；未指定时查询 --python 对应的 site-packages
* `-p, --python FILE`: 目标 Python 解释器路径，默认使用当前解释器
* `-q, --quiet`: 文件不存在时静默退出 0
* `--help`: Show this message and exit.

### `ai-assistant httpx-rfc-cache status`

查看 RFC HTTP cache .pth 补丁是否已安装及其内容。

Usage examples::

    ai-assistant httpx-rfc-cache status
    ai-assistant httpx-rfc-cache status --python .venv/bin/python

**Usage**:

```console
$ ai-assistant httpx-rfc-cache status [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录；未指定时查询 --python 对应的 site-packages
* `-p, --python FILE`: 目标 Python 解释器路径，默认使用当前解释器
* `--help`: Show this message and exit.

## `ai-assistant lan-ddns`

**Usage**:

```console
$ ai-assistant lan-ddns [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `update`: 用 MAC 定位局域网设备 IP 并更新 Cloudflare A 记录

### `ai-assistant lan-ddns update`

用 MAC 定位局域网设备 IP 并更新 Cloudflare A 记录

默认只读本机 ARP 缓存 (零网络流量); 缓存里没有该 MAC 时直接跳过。
需要主动 ping 扫描全网段来补全缓存时, 显式加 --sweep。

使用示例:
- 单次 (仅查 ARP): `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com`
- 允许扫描:        `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com --sweep`
- 守护:            `ai-assistant lan-ddns update -m aa:bb:cc:dd:ee:ff -d nas.example.com -i 300`

**Usage**:

```console
$ ai-assistant lan-ddns update [OPTIONS]
```

**Options**:

* `-m, --mac TEXT`: 目标设备的 MAC 地址  [required]
* `-d, --domain TEXT`: 要更新的 A 记录 FQDN, 如 nas.example.com  [required]
* `-t, --token TEXT`: Cloudflare API Token, 缺省读环境变量 CLOUDFLARE_API_TOKEN
* `-z, --zone TEXT`: Cloudflare zone 名, 缺省按域名自动匹配
* `--sweep / --no-sweep`: ARP 缓存里没有时, 是否主动 ping 扫描全网段补全 (公司内网慎用, 默认关闭)  [default: no-sweep]
* `--subnet TEXT`: --sweep 时指定扫描网段 CIDR, 如 192.168.1.0/24; 缺省自动推导
* `--interface TEXT`: --sweep 时限定使用的网卡名
* `--ttl INTEGER`: DNS TTL, 1 表示 auto  [default: 1]
* `--proxied / --no-proxied`: 是否经 Cloudflare 代理 (橙云)  [default: no-proxied]
* `--ping-timeout FLOAT`: --sweep 时单个地址 ping 超时, 秒  [default: 1.0]
* `--workers INTEGER`: --sweep 时并发扫描线程数  [default: 64]
* `-i, --interval FLOAT`: 循环间隔秒数, 0 表示只执行一次  [default: 0]
* `--dry-run`: 只打印将要执行的变更, 不真正调用 API
* `--help`: Show this message and exit.

## `ai-assistant mcd`

**Usage**:

```console
$ ai-assistant mcd [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `single`: 运行单次对话查询
* `quickstart`: 运行预设的演示查询（多个场景）
* `interactive`: 交互式对话模式

### `ai-assistant mcd single`

运行单次对话查询

**Usage**:

```console
$ ai-assistant mcd single [OPTIONS] QUERY
```

**Arguments**:

* `QUERY`: 用户问题，例如：看一下我有多少张优惠券  [required]

**Options**:

* `--mcp-token TEXT`: MCD MCP 服务的 Authorization token  [env var: MCD_MCP_TOKEN; required]
* `--base-url TEXT`: OpenAI API 基础 URL  [env var: OPENAI_BASE_URL]
* `--api-key TEXT`: OpenAI API Key  [env var: OPENAI_API_KEY]
* `--model TEXT`: 使用的模型名称  [env var: OPENAI_MODEL]
* `--auto-approve / --no-auto-approve`: 是否自动批准工具调用  [default: auto-approve]
* `--verbose / --no-verbose`: 是否打印详细信息  [default: verbose]
* `--help`: Show this message and exit.

### `ai-assistant mcd quickstart`

运行预设的演示查询（多个场景）

**Usage**:

```console
$ ai-assistant mcd quickstart [OPTIONS]
```

**Options**:

* `--mcp-token TEXT`: MCD MCP 服务的 Authorization token  [env var: MCD_MCP_TOKEN; required]
* `--base-url TEXT`: OpenAI API 基础 URL  [env var: OPENAI_BASE_URL]
* `--api-key TEXT`: OpenAI API Key  [env var: OPENAI_API_KEY]
* `--model TEXT`: 使用的模型名称  [env var: OPENAI_MODEL]
* `--auto-approve / --no-auto-approve`: 是否自动批准工具调用  [default: auto-approve]
* `--verbose / --no-verbose`: 是否打印详细信息  [default: verbose]
* `--help`: Show this message and exit.

### `ai-assistant mcd interactive`

交互式对话模式

**Usage**:

```console
$ ai-assistant mcd interactive [OPTIONS]
```

**Options**:

* `--mcp-token TEXT`: MCD MCP 服务的 Authorization token  [env var: MCD_MCP_TOKEN; required]
* `--base-url TEXT`: OpenAI API 基础 URL  [env var: OPENAI_BASE_URL]
* `--api-key TEXT`: OpenAI API Key  [env var: OPENAI_API_KEY]
* `--model TEXT`: 使用的模型名称  [env var: OPENAI_MODEL]
* `--auto-approve / --no-auto-approve`: 是否自动批准工具调用  [default: auto-approve]
* `--help`: Show this message and exit.

## `ai-assistant mcp-cli`

**Usage**:

```console
$ ai-assistant mcp-cli [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `tools`: 以 HTTP Post JSON-RPC 请求方式调用查询可用工具列表

### `ai-assistant mcp-cli tools`

以 HTTP Post JSON-RPC 请求方式调用查询可用工具列表

当前仅支持 streamable MCP 服务端点.

**Usage**:

```console
$ ai-assistant mcp-cli tools [OPTIONS] ENDPOINT
```

**Arguments**:

* `ENDPOINT`: MCP 服务端点  [required]

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant opml`

**Usage**:

```console
$ ai-assistant opml [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `fetch`: 从 OPML 文件中读取 RSS 源并抓取

### `ai-assistant opml fetch`

从 OPML 文件中读取 RSS 源并抓取

使用示例::

    # 基本用法：抓取一次
    ai-assistant opml fetch ~/feeds.opml

    # 设置最大并发数为 10
    ai-assistant opml fetch ~/feeds.opml -m 10

    # 循环抓取
    ai-assistant opml fetch ~/feeds.opml --loop

    # 遇到 429 后跳过该 URL 60 分钟
    ai-assistant opml fetch ~/feeds.opml --rate-limit-minutes 60

    # 组合使用：并发 10、循环抓取、DEBUG 日志
    ai-assistant opml fetch ~/feeds.opml -m 10 --loop --log-level DEBUG

**Usage**:

```console
$ ai-assistant opml fetch [OPTIONS] OPML_PATH
```

**Arguments**:

* `OPML_PATH`: OPML 文件路径  [required]

**Options**:

* `-m, --max-concurrent INTEGER`: 最大并发数  [default: 5]
* `--loop / --no-loop`: 是否循环抓取  [default: no-loop]
* `--log-level TEXT`: 日志级别 (DEBUG, INFO, WARNING, ERROR)  [default: INFO]
* `--rate-limit-minutes INTEGER RANGE`: 遇到 429 后跳过该 URL 的分钟数，也可通过环境变量 OPML_429_SKIP_MINUTES 设置  [env var: OPML_429_SKIP_MINUTES; default: 5; x&gt;=1]
* `--help`: Show this message and exit.

## `ai-assistant plugins`

**Usage**:

```console
$ ai-assistant plugins [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List ai-assistant companion plugins.
* `config-snippet`: Print manual hook configuration for a plugin.
* `install-guide`: Print instructions for agent-assisted...

### `ai-assistant plugins list`

List ai-assistant companion plugins.

Direct install commands:
  codex plugin marketplace add qsoyq/ai-assistant
  codex plugin add agent-bark-notify-codex@ai-assistant
  claude plugin marketplace add qsoyq/ai-assistant
  claude plugin install agent-bark-notify@ai-assistant --scope user
  openclaw plugins install --link ./plugins/agent-bark-notify-openclaw
  openclaw plugins enable agent-bark-notify-openclaw

**Usage**:

```console
$ ai-assistant plugins list [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `ai-assistant plugins config-snippet`

Print manual hook configuration for a plugin.

**Usage**:

```console
$ ai-assistant plugins config-snippet [OPTIONS] PLUGIN
```

**Arguments**:

* `PLUGIN`: Plugin name, e.g. agent-bark-notify  [required]

**Options**:

* `--target [codex|claude|openclaw]`: Target agent: codex, claude, or openclaw.  [required]
* `--scope [global|project]`: Config scope: global or project.  [default: global]
* `--help`: Show this message and exit.

### `ai-assistant plugins install-guide`

Print instructions for agent-assisted plugin installation.

**Usage**:

```console
$ ai-assistant plugins install-guide [OPTIONS] PLUGIN
```

**Arguments**:

* `PLUGIN`: Plugin name, e.g. agent-bark-notify  [required]

**Options**:

* `--target [codex|claude|openclaw]`: Target agent: codex, claude, or openclaw.  [required]
* `--scope [global|project]`: Plugin install scope: global or project.  [default: global]
* `--help`: Show this message and exit.

## `ai-assistant pypi-mirror`

**Usage**:

```console
$ ai-assistant pypi-mirror [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant pypi-upload`

**Usage**:

```console
$ ai-assistant pypi-upload [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

## `ai-assistant reality`

**Usage**:

```console
$ ai-assistant reality [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `build`: 生成 Xray REALITY 服务端配置 / 客户端信息 / vless URL。

### `ai-assistant reality build`

生成 Xray REALITY 服务端配置 / 客户端信息 / vless URL。

Usage examples::

    # 在 Linux 服务器以 root 身份生成并部署
    sudo ai-assistant reality build

    # 在 macOS 预览即将下发的配置, 不动任何文件
    ai-assistant reality build --dry-run --address 1.2.3.4 \
        --public-key &lt;pbk&gt; --private-key &lt;prv&gt;

    # 重用已有 xray 安装, 仅刷新配置并重启服务
    sudo ai-assistant reality build --skip-install

**Usage**:

```console
$ ai-assistant reality build [OPTIONS]
```

**Options**:

* `--port INTEGER`: 监听端口, 缺省为 443
* `--sni TEXT`: 伪装目标域名 (SNI), 缺省为 www.amazon.com
* `--sniff / --no-sniff`: 是否启用 sniffing, 缺省关闭
* `--short-ids TEXT`: REALITY shortIds, 缺省为 88
* `--uuid TEXT`: VLESS 客户端 UUID, 缺省自动生成
* `--public-key TEXT`: REALITY 公钥, 必须与 --private-key 一同提供
* `--private-key TEXT`: REALITY 私钥, 必须与 --public-key 一同提供
* `--address TEXT`: 服务器公网 IP, 缺省时通过 cloudflare/cdn-cgi/trace 自动探测
* `--loglevel TEXT`: xray 日志级别  [default: warning]
* `--access-log TEXT`: xray access 日志路径, 留空则不写入  [default: /var/log/xray/access.log]
* `--error-log TEXT`: xray error 日志路径, 留空则不写入  [default: /var/log/xray/error.log]
* `--limit-fallback / --no-limit-fallback`: 是否启用回落限速, 启用后参数随机生成  [default: no-limit-fallback]
* `--config-path PATH`: 服务端配置写入路径  [default: /usr/local/etc/xray/config.json]
* `--client-info-path PATH`: 客户端信息写入路径  [default: /usr/local/etc/xray/reclient.json]
* `--skip-install`: 跳过 xray 自动安装步骤
* `-y, --yes`: 跳过 xray 安装的二次确认 (curl-bash)
* `--skip-enable`: 跳过 systemctl enable / restart 步骤
* `--dry-run`: 仅渲染并打印配置, 不写盘 / 不安装 / 不操作 systemd
* `--interactive`: 缺省值时通过交互式提示补齐
* `--help`: Show this message and exit.

## `ai-assistant realm`

**Usage**:

```console
$ ai-assistant realm [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `generate`: 生成 realm 配置 TOML。
* `show`: 展示已有 realm 配置。
* `validate`: 校验配置文件结构, 失败时打印字段路径并以非零退出。
* `install`: 从 GitHub releases 下载 realm 二进制并安装到...
* `install-service`: 写入 systemd unit 文件 (不调用 systemctl)。
* `uninstall-service`: 删除 systemd unit 文件 (不调用 systemctl)。

### `ai-assistant realm generate`

生成 realm 配置 TOML。

**Usage**:

```console
$ ai-assistant realm generate [OPTIONS]
```

**Options**:

* `--log-level TEXT`: 日志级别, off/error/warn/info/debug/trace  [default: off]
* `--log-output TEXT`: 日志输出路径  [default: /var/log/realm.log]
* `--no-tcp / --no-no-tcp`: 禁用 TCP 转发  [default: no-no-tcp]
* `--use-udp / --no-use-udp`: 启用 UDP 转发  [default: use-udp]
* `--listen-host TEXT`: 本地监听主机地址  [default: [::0]]
* `--listen-port TEXT`: 本地监听端口, 支持单端口或范围, 如 443,8110-8113  [default: 443]
* `--remote-host TEXT`: 远程主机地址  [default: 127.0.0.1]
* `--remote-port TEXT`: 远程主机端口  [default: 443]
* `--output TEXT`: 配置输出路径, 默认 - 输出到 stdout  [default: -]
* `--help`: Show this message and exit.

### `ai-assistant realm show`

展示已有 realm 配置。

**Usage**:

```console
$ ai-assistant realm show [OPTIONS] [PATH]
```

**Arguments**:

* `[PATH]`: 配置路径, 留空时按 ./config.toml -&gt; /etc/realm/config.toml 顺序查找

**Options**:

* `--help`: Show this message and exit.

### `ai-assistant realm validate`

校验配置文件结构, 失败时打印字段路径并以非零退出。

**Usage**:

```console
$ ai-assistant realm validate [OPTIONS] [PATH]
```

**Arguments**:

* `[PATH]`: 配置路径, 留空时按 ./config.toml -&gt; /etc/realm/config.toml 顺序查找

**Options**:

* `--help`: Show this message and exit.

### `ai-assistant realm install`

从 GitHub releases 下载 realm 二进制并安装到 --prefix (仅 Linux)。

**Usage**:

```console
$ ai-assistant realm install [OPTIONS]
```

**Options**:

* `--version TEXT`: realm 版本标签, latest 自动解析 GitHub 最新; 显式形如 v2.9.3  [default: latest]
* `--arch TEXT`: CPU 架构, 可选 [&#x27;aarch64&#x27;, &#x27;x86_64&#x27;]  [default: x86_64]
* `--prefix PATH`: 二进制安装目录  [default: /usr/local/bin]
* `--force / --no-force`: 目标已存在时覆盖  [default: no-force]
* `--dry-run / --no-dry-run`: 只打印将执行的步骤, 不下载也不写盘  [default: no-dry-run]
* `--help`: Show this message and exit.

### `ai-assistant realm install-service`

写入 systemd unit 文件 (不调用 systemctl)。

写入完成后请手动执行:

  sudo systemctl daemon-reload
  sudo systemctl enable --now realm

校验状态:

  systemctl status realm

**Usage**:

```console
$ ai-assistant realm install-service [OPTIONS]
```

**Options**:

* `--config PATH`: ExecStart -c 指向的配置文件路径  [default: /etc/realm/config.toml]
* `--binary PATH`: ExecStart 使用的 realm 二进制路径  [default: /usr/local/bin/realm]
* `--unit-path PATH`: systemd unit 文件写入路径  [default: /etc/systemd/system/realm.service]
* `--force / --no-force`: 已存在时覆盖, 避免误盖手改过的 unit  [default: no-force]
* `--dry-run / --no-dry-run`: 只打印将写入的内容, 不写盘  [default: no-dry-run]
* `--help`: Show this message and exit.

### `ai-assistant realm uninstall-service`

删除 systemd unit 文件 (不调用 systemctl)。

删除前请先停用 service:

  sudo systemctl disable --now realm

删除后请手动执行:

  sudo systemctl daemon-reload

**Usage**:

```console
$ ai-assistant realm uninstall-service [OPTIONS]
```

**Options**:

* `--unit-path PATH`: 待删除的 systemd unit 文件路径  [default: /etc/systemd/system/realm.service]
* `--dry-run / --no-dry-run`: 只打印将删除的文件, 不实际删除  [default: no-dry-run]
* `--help`: Show this message and exit.

## `ai-assistant requests-disable-verify`

**Usage**:

```console
$ ai-assistant requests-disable-verify [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `install`: 将 .pth 补丁安装到当前解释器的 site-packages。
* `uninstall`: 移除 site-packages 下的 .pth 补丁。
* `status`: 查看 .pth 补丁是否已安装及其内容。

### `ai-assistant requests-disable-verify install`

将 .pth 补丁安装到当前解释器的 site-packages。

Usage examples::

    ai-assistant requests-disable-verify install
    ai-assistant requests-disable-verify install --yes
    ai-assistant requests-disable-verify install --target ./custom-site-packages

**Usage**:

```console
$ ai-assistant requests-disable-verify install [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 写入目录，默认使用 site.getsitepackages()[0]
* `-y, --yes`: 跳过确认提示直接写入
* `--help`: Show this message and exit.

### `ai-assistant requests-disable-verify uninstall`

移除 site-packages 下的 .pth 补丁。

Usage examples::

    ai-assistant requests-disable-verify uninstall
    ai-assistant requests-disable-verify uninstall --quiet

**Usage**:

```console
$ ai-assistant requests-disable-verify uninstall [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `-q, --quiet`: 文件不存在时静默退出 0
* `--help`: Show this message and exit.

### `ai-assistant requests-disable-verify status`

查看 .pth 补丁是否已安装及其内容。

Usage examples::

    ai-assistant requests-disable-verify status

**Usage**:

```console
$ ai-assistant requests-disable-verify status [OPTIONS]
```

**Options**:

* `-t, --target DIRECTORY`: 自定义 .pth 所在目录，默认使用 site.getsitepackages()[0]
* `--help`: Show this message and exit.

## `ai-assistant route`

**Usage**:

```console
$ ai-assistant route [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: 列出本工具管理的路由, 并尽量校验当前系统状态。
* `add`: 添加一条运行时 managed route。
* `delete`: 删除一条 managed route。
* `query`: 查询某个 IP 当前实际匹配的系统路由。

### `ai-assistant route list`

列出本工具管理的路由, 并尽量校验当前系统状态。

默认只读取本工具状态文件里的 managed routes。系统路由表通常无法说明一条
路由是谁添加的, 因此本命令不会把 VPN、Docker、DHCP、MDM 或其他工具添加的
路由误报为 managed route。

使用示例:
- ai-assistant route list
- ai-assistant route list --state-file ./routes.json
- ai-assistant route list --all-system

**Usage**:

```console
$ ai-assistant route list [OPTIONS]
```

**Options**:

* `--all-system`: 显示系统原始路由表。注意: 这不是 managed route 列表, 不能据此判断哪些是自定义路由。
* `--state-file PATH`: managed route JSON 状态文件路径; 默认使用 AI_ASSISTANT_ROUTE_STATE 或用户 state 目录。
* `--help`: Show this message and exit.

### `ai-assistant route add`

添加一条运行时 managed route。

add 成功后会写入本工具状态文件, 后续 list/delete 默认只管理这些记录。
本命令通常需要管理员权限: macOS/Linux 建议用 sudo 运行, Windows 需要管理员
PowerShell/CMD。

使用示例:
- sudo ai-assistant route add --dest 10.0.0.0/8 --gateway 192.168.1.1
- sudo ai-assistant route add --dest 10.20.0.0/16 --gateway 192.168.1.1 --interface en0 --metric 20
- sudo ai-assistant route add --dest 10.20.0.0/16 --gateway 198.51.100.254 --macos-global
- ai-assistant route add --dest 10.0.0.0/8 --gateway 192.168.1.1 --dry-run

**Usage**:

```console
$ ai-assistant route add [OPTIONS]
```

**Options**:

* `--dest TEXT`: 目标网段 CIDR, 如 10.0.0.0/8 或 2001:db8::/32。必须包含前缀长度。  [required]
* `--gateway TEXT`: 下一跳网关 IP, 必须和 --dest 使用同一地址族。  [required]
* `-i, --interface TEXT`: 可选出口网卡名/接口别名, 如 macOS en0、Linux eth0、Windows Ethernet。
* `--metric INTEGER`: 可选路由 metric/优先级。不同平台语义略有差异。
* `--macos-global`: [仅 macOS] 通过 PF_ROUTE socket 以非 scoped 形式添加全局路由 (请求 RTF_GLOBAL, 内核可能忽略该标志), 避免路由被 -ifscope 后在全局查找中失效。用于 VPN (如 Tailscale accept-routes) 子网路由遮蔽物理网卡路由的场景。仅 IPv4, 不可与 --interface 同用, 需要 sudo。
* `--dry-run`: 只打印将执行的平台命令, 不修改系统路由表, 也不写状态文件。
* `--state-file PATH`: managed route JSON 状态文件路径。
* `--help`: Show this message and exit.

### `ai-assistant route delete`

删除一条 managed route。

默认只删除本工具状态文件里存在的 managed route, 避免误删 VPN、Docker、公司
MDM 或其他工具添加的系统路由。确实要删除 unmanaged route 时必须显式使用
--unmanaged --dest ... --gateway ...。

使用示例:
- sudo ai-assistant route delete 7bb0e5a99a2c
- sudo ai-assistant route delete --dest 10.0.0.0/8 --gateway 192.168.1.1
- sudo ai-assistant route delete --dest 10.0.0.0/8 --all-matching
- ai-assistant route delete 7bb0e5a99a2c --force-state
- sudo ai-assistant route delete --unmanaged --dest 10.0.0.0/8 --gateway 192.168.1.1

**Usage**:

```console
$ ai-assistant route delete [OPTIONS] [ROUTE_ID]
```

**Arguments**:

* `[ROUTE_ID]`: managed route ID, 可从 `ai-assistant route list` 获取。

**Options**:

* `--dest TEXT`: 按目标网段删除 managed route; 多条匹配时请改用 route ID 或显式加 --all-matching。
* `--gateway TEXT`: 和 --dest 一起精确匹配下一跳网关。
* `--all-matching`: 当 --dest/--gateway 匹配多条 managed routes 时, 显式删除全部匹配项。
* `--unmanaged`: 允许删除未记录在状态文件中的系统路由。危险选项, 必须同时提供 --dest 和 --gateway。
* `--force-state`: 只清理状态文件中的 managed route, 不执行系统 delete。用于系统路由已手动删除的 stale 记录。
* `--dry-run`: 只打印将执行的平台命令, 不修改系统路由表或状态文件。
* `--state-file PATH`: managed route JSON 状态文件路径。
* `--help`: Show this message and exit.

### `ai-assistant route query`

查询某个 IP 当前实际匹配的系统路由。

本命令委托系统自己的路由决策查询能力, 不在 Python 里重新实现 longest-prefix
match。Linux 使用 `ip route get`, macOS 使用 `route -n get`, Windows 使用
`Find-NetRoute`。

使用示例:
- ai-assistant route query 8.8.8.8
- ai-assistant route query 10.1.2.3
- ai-assistant route query 2001:4860:4860::8888

**Usage**:

```console
$ ai-assistant route query [OPTIONS] IP
```

**Arguments**:

* `IP`: 要查询的目标 IP, 如 8.8.8.8 或 2001:4860:4860::8888。  [required]

**Options**:

* `--state-file PATH`: managed route JSON 状态文件路径; 用于提示该 IP 是否落入某条 managed route 的目标网段。
* `--help`: Show this message and exit.

## `ai-assistant similar-questions`

**Usage**:

```console
$ ai-assistant similar-questions [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `generate`: 输入问题并输出 N 条相似问题

### `ai-assistant similar-questions generate`

输入问题并输出 N 条相似问题

**Usage**:

```console
$ ai-assistant similar-questions generate [OPTIONS] QUERY
```

**Arguments**:

* `QUERY`: 用户输入问题  [required]

**Options**:

* `--topn INTEGER`: 生成的相似问条数  [default: 5]
* `--base-url TEXT`
* `--api-key TEXT`
* `--model TEXT`
* `--help`: Show this message and exit.

## `ai-assistant ssl`

**Usage**:

```console
$ ai-assistant ssl [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `info`: 查看证书信息并打印。
* `generate`: 通过交互方式生成自签名 SSL 证书。
* `trust`: 将证书加入系统信任存储。
* `merge`: 合并多个证书文件为一个 PEM bundle。

### `ai-assistant ssl info`

查看证书信息并打印。

Usage examples::

    # 打印证书详细信息
    ai-assistant ssl info ./ssl/server.crt

**Usage**:

```console
$ ai-assistant ssl info [OPTIONS] CERT_PATH
```

**Arguments**:

* `CERT_PATH`: 证书文件路径  [required]

**Options**:

* `--help`: Show this message and exit.

### `ai-assistant ssl generate`

通过交互方式生成自签名 SSL 证书。

Usage examples::

    # 使用默认输出目录（当前目录下的 ssl/）
    ai-assistant ssl generate

    # 指定证书输出目录
    ai-assistant ssl generate --output-dir ./certs

**Usage**:

```console
$ ai-assistant ssl generate [OPTIONS]
```

**Options**:

* `-o, --output-dir DIRECTORY`: 证书输出目录，默认使用当前目录下的 ssl 子目录
* `--help`: Show this message and exit.

### `ai-assistant ssl trust`

将证书加入系统信任存储。

Usage examples::

    # 将证书加入系统信任存储
    ai-assistant ssl trust ./ssl/server.crt

    # 在 macOS / Windows 中仅信任当前用户
    ai-assistant ssl trust ./ssl/server.crt --scope user

**Usage**:

```console
$ ai-assistant ssl trust [OPTIONS] CERT_PATH
```

**Arguments**:

* `CERT_PATH`: 需要加入系统信任存储的证书文件路径  [required]

**Options**:

* `--scope TEXT`: 证书信任范围：system 表示系统级，user 表示当前用户（Linux 仅支持 system）  [default: system]
* `--help`: Show this message and exit.

### `ai-assistant ssl merge`

合并多个证书文件为一个 PEM bundle。

自动按文件内容识别 PEM、DER、PKCS#7（PEM/DER）和 PKCS#12 格式。
输出始终是 PEM bundle。

生成 bundle 后，可通过环境变量让常见工具识别新的 CA 文件
（以 `~/.ca-bundle.pem` 为例，按需替换路径）：


- OpenSSL / Python `ssl` / httpx: export SSL_CERT_FILE=~/.ca-bundle.pem
- requests: export REQUESTS_CA_BUNDLE=~/.ca-bundle.pem
- curl: export CURL_CA_BUNDLE=~/.ca-bundle.pem
- git: git config --global http.sslCAInfo ~/.ca-bundle.pem
- Node.js: export NODE_EXTRA_CA_CERTS=~/.ca-bundle.pem
- AWS CLI / boto3: export AWS_CA_BUNDLE=~/.ca-bundle.pem

Windows PowerShell 可用 `setx SSL_CERT_FILE &quot;%USERPROFILE%\.ca-bundle.pem&quot;` 等价写法。

Usage examples::

    # 合并 certifi 自带的 CA 与自签 CA，写入文件
    ai-assistant ssl merge $(python -m certifi) ~/certs/my-root-ca.cer -o ~/.ca-bundle.pem

    # 从标准输入追加一个证书
    cat extra.crt | ai-assistant ssl merge cacert.pem -

    # 合并 PKCS#12（需要密码）
    ai-assistant ssl merge bundle.pem client.p12 --password secret -o merged.pem

**Usage**:

```console
$ ai-assistant ssl merge [OPTIONS] FILES...
```

**Arguments**:

* `FILES...`: 证书文件路径，可传多个；使用 `-` 表示从标准输入读取  [required]

**Options**:

* `-o, --output FILE`: 输出文件路径，未指定则写入标准输出
* `--dedup / --no-dedup`: 按 SHA-256 指纹去重，默认开启  [default: dedup]
* `--headers / --no-headers`: 在每个证书前输出 Subject/Issuer 注释  [default: headers]
* `--password TEXT`: PKCS#12 文件密码，留空表示无密码
* `--help`: Show this message and exit.

## `ai-assistant stash-log`

**Usage**:

```console
$ ai-assistant stash-log [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `download`: 下载抓包日志中的图片和视频
* `urls`: 提取抓包日志中的所有请求 URL

### `ai-assistant stash-log download`

下载抓包日志中的图片和视频

使用示例:
- `ai-assistant stash-log download access.log`
- `ai-assistant stash-log download access.log -o shcp`

**Usage**:

```console
$ ai-assistant stash-log download [OPTIONS] FILE
```

**Arguments**:

* `FILE`: 日志文件路径  [required]

**Options**:

* `-o, --output-dir TEXT`: 下载输出目录前缀  [default: Assets]
* `--help`: Show this message and exit.

### `ai-assistant stash-log urls`

提取抓包日志中的所有请求 URL

使用示例:
- `ai-assistant stash-log urls access.log`
- `ai-assistant stash-log urls access.log --dest output.txt`
- `ai-assistant stash-log urls access.log --no-uniq --no-sort`

**Usage**:

```console
$ ai-assistant stash-log urls [OPTIONS] FILE
```

**Arguments**:

* `FILE`: 日志文件路径  [required]

**Options**:

* `--dest PATH`: 结果输出路径, 默认标准输出  [default: -]
* `--uniq`: 去重  [default: True]
* `--sort`: 排序  [default: True]
* `--help`: Show this message and exit.

## `ai-assistant tg-bot-click`

Telegram bot 自动点击工具。

向指定 bot 发送一条触发消息, 在等待时间内监听回复, 找到包含指定文本的
回复后点击按钮。默认点击命中消息中的第一个按钮; 如果消息有多个按钮,
建议使用 --button-text 精确指定要点击的按钮文本。

这个命令通过 Telegram MTProto 使用你的用户账号登录。首次使用时可能需要
输入 Telegram 验证码; 如果账号开启了 2FA, 还会提示输入 2FA 密码。登录态
保存为本地 session 文件, 后续定时任务可复用。

Session 文件等同于账号登录凭据, 请按敏感文件保护。默认 session 位于用户
state 目录, 也可以通过 --session 指定已有 session 文件, 或用
--export-session / --import-session 在机器之间迁移。

使用示例:
- 发送 /start, 等待包含“签到”的回复, 然后点击第一个按钮:
  ai-assistant tg-bot-click @example_bot --trigger /start --match 签到
- 使用环境变量提供 Telegram 凭据:
  TG_API_ID=123 TG_API_HASH=xxx TG_PHONE=+8613xxx ai-assistant tg-bot-click @example_bot --match 签到
- 多按钮回复中按按钮文本点击:
  ai-assistant tg-bot-click @example_bot --match 签到 --button-text 签到
- 导出默认 session 文件:
  ai-assistant tg-bot-click --export-session ./telegram.session
- 导入已有 session 到默认位置:
  ai-assistant tg-bot-click --import-session ./telegram.session

**Usage**:

```console
$ ai-assistant tg-bot-click [OPTIONS] [BOT]
```

**Arguments**:

* `[BOT]`: 目标 Telegram bot 用户名, 可带或不带 @。导入/导出 session 时可省略。

**Options**:

* `-v, -V, --version`
* `--trigger TEXT`: 发送给 bot 的触发语, 默认 /start。  [default: /start]
* `--match TEXT`: 待匹配的回复文本; 命中条件为回复正文包含该文本。
* `--timeout FLOAT RANGE`: 等待匹配回复的总超时时间, 秒。  [default: 30.0; x&gt;=0.1]
* `--button-text TEXT`: 可选按钮文本。未指定时点击命中消息中的第一个按钮。
* `--api-id INTEGER`: Telegram API ID, 也可通过 TG_API_ID 提供。  [env var: TG_API_ID]
* `--api-hash TEXT`: Telegram API hash, 也可通过 TG_API_HASH 提供。  [env var: TG_API_HASH]
* `--phone TEXT`: Telegram 账号手机号, 也可通过 TG_PHONE 提供。  [env var: TG_PHONE]
* `--session PATH`: Telegram session 文件路径; 默认使用用户 state 目录。  [env var: TG_SESSION]
* `--export-session PATH`: 把当前 --session 或默认 session 文件复制到指定路径, 用于备份/迁移。
* `--import-session PATH`: 把已有 session 文件复制到当前 --session 或默认 session 位置。
* `-f, --force`: 导入/导出 session 时允许覆盖目标文件。
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

## `ai-assistant udp`

**Usage**:

```console
$ ai-assistant udp [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `client`: 创建 UDP 客户端, 发送消息并监听回复
* `echo-server`: 启动 UDP Echo 服务器, 收到的内容原样回发

### `ai-assistant udp client`

创建 UDP 客户端, 发送消息并监听回复

使用示例:
- `ai-assistant udp client &quot;ping&quot; -h 1.2.3.4 -p 8000`

**Usage**:

```console
$ ai-assistant udp client [OPTIONS] [MESSAGE]
```

**Arguments**:

* `[MESSAGE]`: 发送的消息  [default: hello world]

**Options**:

* `-h, --host TEXT`: 服务端地址  [default: 127.0.0.1]
* `-p, --port INTEGER`: 服务端端口  [default: 8000]
* `-t, --timeout FLOAT`: 接收超时, 秒  [default: 60]
* `--help`: Show this message and exit.

### `ai-assistant udp echo-server`

启动 UDP Echo 服务器, 收到的内容原样回发

使用示例:
- `ai-assistant udp echo-server -p 8000`

**Usage**:

```console
$ ai-assistant udp echo-server [OPTIONS]
```

**Options**:

* `-h, --host TEXT`: 监听地址  [default: 0.0.0.0]
* `-p, --port INTEGER`: 监听端口  [default: 8000]
* `--help`: Show this message and exit.

## `ai-assistant uv-tool`

**Usage**:

```console
$ ai-assistant uv-tool [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `upgrade-all`: 升级所有通过 uv tool 安装的工具, 逐个执行并汇总结果。

### `ai-assistant uv-tool upgrade-all`

升级所有通过 uv tool 安装的工具, 逐个执行并汇总结果。

**Usage**:

```console
$ ai-assistant uv-tool upgrade-all [OPTIONS]
```

**Options**:

* `--dry-run`: 只列出会被升级的工具, 不执行
* `--prerelease TEXT`: 透传 uv tool upgrade --prerelease 的取值, 例如 allow / if-necessary / explicit
* `--reinstall`: 透传 uv tool upgrade --reinstall, 强制重装
* `--help`: Show this message and exit.

## `ai-assistant win-env`

**Usage**:

```console
$ ai-assistant win-env [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: 列出环境变量。
* `get`: 查看变量值。默认 --scope all 同时打印 user / system /...
* `set`: 新增或修改变量 (覆盖写入)。
* `unset`: 删除变量。
* `path`: PATH 专用操作 (add / remove / show)

### `ai-assistant win-env list`

列出环境变量。

**Usage**:

```console
$ ai-assistant win-env list [OPTIONS]
```

**Options**:

* `-s, --scope [user|system|process|all]`: user / system / process / all  [default: user]
* `--json`: JSON 输出
* `--help`: Show this message and exit.

### `ai-assistant win-env get`

查看变量值。默认 --scope all 同时打印 user / system / process 三个源。

**Usage**:

```console
$ ai-assistant win-env get [OPTIONS] NAME
```

**Arguments**:

* `NAME`: 变量名  [required]

**Options**:

* `-s, --scope [user|system|process|all]`: [default: all]
* `--json`
* `--help`: Show this message and exit.

### `ai-assistant win-env set`

新增或修改变量 (覆盖写入)。

**Usage**:

```console
$ ai-assistant win-env set [OPTIONS] NAME VALUE
```

**Arguments**:

* `NAME`: 变量名  [required]
* `VALUE`: 变量值  [required]

**Options**:

* `-s, --scope [user|system]`: [default: user]
* `--type [sz|expand]`: sz | expand; 不传时沿用现值或自动推断
* `--dry-run`
* `--help`: Show this message and exit.

### `ai-assistant win-env unset`

删除变量。

**Usage**:

```console
$ ai-assistant win-env unset [OPTIONS] NAME
```

**Arguments**:

* `NAME`: 变量名  [required]

**Options**:

* `-s, --scope [user|system]`: [default: user]
* `--dry-run`
* `--help`: Show this message and exit.

### `ai-assistant win-env path`

PATH 专用操作 (add / remove / show)

**Usage**:

```console
$ ai-assistant win-env path [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `show`: 显示 PATH 各 entry。effective = 当前进程实际生效的 PATH。
* `add`: 向 PATH 加入一个目录, 自动去重并保留 REG_EXPAND_SZ 类型。
* `remove`: 从 PATH 移除一个目录 (大小写不敏感, normpath 比较)。

#### `ai-assistant win-env path show`

显示 PATH 各 entry。effective = 当前进程实际生效的 PATH。

**Usage**:

```console
$ ai-assistant win-env path show [OPTIONS]
```

**Options**:

* `-s, --scope [user|system|effective]`: [default: effective]
* `--help`: Show this message and exit.

#### `ai-assistant win-env path add`

向 PATH 加入一个目录, 自动去重并保留 REG_EXPAND_SZ 类型。

**Usage**:

```console
$ ai-assistant win-env path add [OPTIONS] ENTRY
```

**Arguments**:

* `ENTRY`: 要加入的目录  [required]

**Options**:

* `-s, --scope [user|system]`: [default: user]
* `--prepend`: 加到最前; 默认追加到末尾
* `--backup-dir PATH`: 备份目录, 默认 %LOCALAPPDATA%/ai-assistant/win-env-backup
* `--dry-run`
* `--help`: Show this message and exit.

#### `ai-assistant win-env path remove`

从 PATH 移除一个目录 (大小写不敏感, normpath 比较)。

**Usage**:

```console
$ ai-assistant win-env path remove [OPTIONS] ENTRY
```

**Arguments**:

* `ENTRY`: 要移除的目录  [required]

**Options**:

* `-s, --scope [user|system]`: [default: user]
* `--backup-dir PATH`
* `--dry-run`
* `--help`: Show this message and exit.
