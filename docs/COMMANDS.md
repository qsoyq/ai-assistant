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

* `aliyun-oss`: 阿里云 OSS 工具集
* `cf-tunnel-watcher`: 监听 Cloudflare Tunnel 连接状态变化并执行命令
* `cookies`: 从本地浏览器中提取指定域名的 Cookie。
* `cursor-usage`: Get usage of Cursor.
* `disable-ssl-verify`: 聚合命令：同时管理 httpx 和 requests 的 SSL verify 禁用补丁。
* `docker`: Docker 相关工具
* `docker-hub-runner`: 监听 Docker Hub 镜像最新推送并执行命令
* `file-change-runner`: 监听文件变化并执行命令
* `freshrss`: FreshRSS 工具集.
* `greader`: Google Reader API 客户端工具
* `handoff`: macOS Handoff 操作工具
* `httpx-disable-verify`: 通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 httpx 的 SSL verify。
* `mcd`: 基于 OpenAI Responses API 的 mcp-mcd 工具
* `mcp-cli`: MCP Client
* `opml`: Fetch RSS feeds from OPML file periodically.
* `reality`: 基于 Xray REALITY 协议生成服务端与客户端配置, 可选自动安装 xray 并启用 systemd 服务。
* `requests-disable-verify`: 通过 site-packages 下的 .pth 文件，对当前 Python 解释器全局禁用 requests 的 SSL verify。
* `similar-questions`: Generate N similar questions by input query.
* `ssl`: 生成和管理 SSL 证书
* `stash-log`: Stash 抓包日志解析工具
* `udp`: UDP 端口可达性验证工具

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
