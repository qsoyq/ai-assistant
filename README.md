# ai-assistant

个人开发用的 CLI 工具集，一个二进制 + 22 个子命令，覆盖 SSL/网络/存储/RSS/容器/macOS 自动化等日常碎片任务。

完整命令参考见 [docs/COMMANDS.md](docs/COMMANDS.md)（typer 自动生成，递归覆盖每个 Argument/Option/env var）。

## 安装

默认安装只带轻量依赖，重命令通过 extras 按需启用。

```shell
# 最小安装（含 udp / opml / ssl / disable-verify / handoff 等轻量命令）
uv tool install git+https://github.com/qsoyq/ai-assistant.git

# 全量安装（含 mcd / aliyun-oss / freshrss / docker / cookies / cursor-usage）
uv tool install 'git+https://github.com/qsoyq/ai-assistant.git#egg=ai-assistant[all]'

# 一次性运行（uvx）
uvx ai-assistant --help
uvx 'ai-assistant[mcd]' ai-assistant mcd quickstart
```

如果某条命令依赖未装，命令会打印明确的 `pip install 'ai-assistant[<extra>]'` 提示，不会抛 raw traceback。

可选 extras：

| extra | 触发命令 | 拉入的依赖 |
|---|---|---|
| `mcd` | `mcd`, `similar-questions` | `openai` |
| `oss` | `aliyun-oss` | `oss2` |
| `freshrss` | `freshrss` | `sqlalchemy` + `pymysql` + `psycopg[binary]` |
| `docker` | `docker` | `docker` SDK |
| `cookies` | `cookies` | `browser-cookie3` |
| `cursor` | `cursor-usage` | `matplotlib` + `pandas` |
| `telegram` | `tg-bot-click` | `telethon` |
| `shell-env` | `shell-env-to-win`（Windows） | `bashkit==0.18.2` |
| `cindy` | `cindy` 的 zstd 压缩与交互选择增强 | `zstandard` + `questionary`（无此 extra 时可用不压缩归档与编号选择） |
| `all` | 全部 | 上述并集 |

## Cindy 数据与客户端管理

`ai-assistant cindy --help` 使用中文说明；枚举参数的帮助显式列出可选值、含义和默认规则。现有 `cshare-to-markdown` 保持兼容。

```bash
# 冷备份：操作期间所有地区的 Cindy 都必须完全退出
ai-assistant cindy data backup --region cn --label before-test
# reset 已默认生成并校验 pre-reset 备份
ai-assistant cindy data reset --region cn
ai-assistant cindy data restore --region cn
ai-assistant cindy recover

# 在 POSIX 主机上只下载 Windows 国际版安装器，不执行安装
ai-assistant cindy install --region global --channel beta --platform win32 --arch x64 --mode installer --download-only

# macOS：两区程序放在不同目录，userData 仍由客户端按区域选择
ai-assistant cindy install --region cn --dest "$HOME/Applications/Cindy-CN/Cindy.app"
ai-assistant cindy install --region global --dest "$HOME/Applications/Cindy-Global/Cindy.app"
ai-assistant cindy installs --json
```

私有状态默认为 `${XDG_STATE_HOME:-~/.local/state}/ai-assistant/cindy`，可用绝对路径 `AI_ASSISTANT_CINDY_HOME` 覆盖。`--backup-dir` 只选择备份目录；迁移恢复目标须同时使用 `--target` 和 `--allow-relocate`。不允许跨地区、平台、原生架构或 Profile 类型恢复。归档包含内嵌文件摘要，丢失索引后仍可完整校验；`data clear` 只能通过真实终端输入确认词删除备份，不提供 `--yes`。

当前已实现 POSIX 数据事务、查询/校验下载和 macOS 安装适配器。Windows 写入（含 DACL/互斥与下载缓存）、Windows 原生安装/卸载，以及 Linux 原生安装和桌面集成尚未通过实机门禁，明确拒绝执行；在 POSIX 主机可下载两者安装包。没有跳过门禁的环境变量。完整边界与验证方法见 [Cindy CLI 设计](docs/design/cindy-cli.md)。

## Shell 环境变量导入 Windows

`shell-env-to-win` 通过 Python 库 Bashkit 执行 Bash 兼容的 Shell 文件，将新增或值发生变化的导出变量写入 Windows。无需安装 Bash、Git Bash 或 WSL；Windows x64 的 Bashkit 预编译 wheel 下载约 15.6 MB。

```powershell
uv tool install 'ai-assistant[shell-env]'

# 执行脚本并预览变量名、字符数和写入动作，不写入 Windows
ai-assistant shell-env-to-win ./paseo.zshrc --dry-run

# 默认写入当前用户变量；同名变量覆盖，采用 REG_SZ
ai-assistant shell-env-to-win ./paseo.zshrc

# 显式提供初始环境；不会自动继承当前进程的环境变量
ai-assistant shell-env-to-win ./settings.bashrc --env 'HOME=/home/user' --env 'MODEL=example'

# 写入系统变量，需要管理员权限
ai-assistant shell-env-to-win ./settings.bashrc --scope system
```

支持多行引号、quoted heredoc、变量展开、函数和条件分支，也支持先赋值再 `export NAME`。例如以下正文中的中文、空行、`$HOME` 和反引号均保持字面内容，末尾换行按 Shell 命令替换规则删除：

```bash
PROMPT="$(cat <<'PROMPT_EOF'
中文第一行

$HOME `literal`
PROMPT_EOF
)"
export PROMPT
```

源文件按 UTF-8 读取，兼容 BOM，LF/CRLF 源文件行结束符读取为 LF。求值后的字符串不额外改写，包括脚本显式转义产生的 CRLF、换行和空白。源目录只读映射为解释器的 `/input`，同时作为工作目录，因此 `source ./other.sh` 可以读取同目录文件。临时文件可写入虚拟 `/tmp`。`HOME` 等变量和绝对路径采用虚拟环境中的值，macOS 路径不会自动转换成 Windows 路径。

此命令采用 **Bash 语义**，文件名为 `.zshrc` 也不会切换到 Zsh；不保证 Zsh 专有语法或 macOS 命令兼容。Bashkit 执行的是其内置命令，不调用宿主程序，网络不启用。未导出的局部变量不导入；与初始环境相同的变量不导入；脚本删除变量也不会删除 Windows 中的变量。

默认跳过 `PATH` 并报告，避免将 Unix 路径覆盖到 Windows；显式传入 `--include-path` 才按原值覆盖，不转换路径或分隔符。脚本在 `set -e` 模式下执行；非零退出、stderr 输出、解析失败或超时（10 秒）会中止整批导入。Windows 不区分变量名大小写，源文件同时导出 `FOO` 和 `foo` 时也会中止。预检成功后才写入；注册表写入不是事务，中途失败会报告已写入的变量，不自动回滚。

写入后同步更新命令自身的 Python 进程环境并广播一次刷新通知。已打开的终端和应用需重新启动才能使用新值。

## ⚠️ 安全提示

### `cindy data` / `cindy install`

备份是选定 userData 目录的内容快照，不是整机备份。可能包含全部对话、日志、插件和明文/密文秘密；不解密凭证、不读取系统钥匙串，不保证同机恢复仍保持登录。外部项目、Agent home、Git worktree 恢复对象和链接目标不包含在快照中。备份与敏感临时目录禁止放入 Git 工作区（包括忽略目录），建议避免自动同步网盘。

restore/reset 会覆盖 Profile，默认先生成且完整校验自动备份；跳过备份后可能无法撤销。恢复只接受可信归档：内嵌摘要检测损坏，但不证明来源可信。默认保留当前 cn 的顶层 shared-*；显式恢复归档 shared 可能影响 global/dev。所有地区客户端必须在整个数据操作期间保持停止；CLI 的互斥锁不能阻止客户端重新启动。发生中断或冲突时保留 journal，通过 `cindy recover` 检查，不能手动删日志假装完成。

安装命令会访问对应地区的 Cindy CDN 与 GitHub，可下载并在明确确认后安装官方程序；macOS 始终检查签名、地区身份和版本。Windows 历史热更 ZIP 必须有该 ZIP 的可信摘要，不能用安装器摘要代替。只有 macOS 本机安装可显式选择无摘要的完整签名校验；下载或签名失败不会自动降低安全要求。

**按目录分开安装只能避免程序文件互相覆盖，不保证双地区完全无冲突。** 两区共用深链协议、部分共享目录和钥匙串身份；客户端启动时可能自行注册协议，Windows 官方安装器还有同名快捷方式、菜单和进程干扰。macOS/Windows 的自动更新没有被关闭，旧版启动后可能自动升级。CLI 不启动客户端、不改签名、不改 ASAR，也不会修改更新链路来掩盖这些限制。

### `shell-env-to-win`

`--dry-run` 仍会在 Bashkit 虚拟环境中执行脚本。命令允许读取源目录中的文件，但该目录只读挂载，不启用宿主命令和网络。输出仅包含变量名、字符数和状态，不打印变量值、脚本日志或包含源代码的解释器错误。实际导入会将变量持久写入 Windows，按环境变量的访问权限保存；不要将包含真实凭据的配置或导出值提交到仓库。

### `disable-ssl-verify` / `httpx-disable-verify` / `requests-disable-verify`

这些命令通过 `.pth` 文件**对当前 venv 内的所有 Python 进程**全局禁用 SSL 证书校验，包括用户显式传入 `verify=True` 或自定义 CA bundle 的情况。

- **不要在生产环境使用**——任何 MITM 都会无声放行。
- 仅适合本地调试受信网络中的自签名证书 / 代理抓包等场景。
- 卸载方式：`ai-assistant disable-ssl-verify uninstall`。

### `httpx-rfc-cache`

这个命令通过 `.pth` 文件**对目标 Python 解释器环境内的所有 Python 进程**启用 `httpx` 的 RFC 9111 HTTP cache transport。它使用 Hishel 包装 `httpx` 默认 transport，显式传入的自定义 transport 不会被覆盖。

- 默认遵循 HTTP cache 标准语义，不会把所有响应无条件缓存。
- 安装前需确保目标解释器能导入 `httpx` 和 `hishel.httpx`。
- 安装示例：`ai-assistant httpx-rfc-cache install --python .venv/bin/python --yes`。
- 临时关闭：`AI_ASSISTANT_HTTPX_RFC_CACHE_DISABLE=1`。
- 卸载方式：`ai-assistant httpx-rfc-cache uninstall --python .venv/bin/python`。

### `reality build` 自动安装 xray

`ai-assistant reality build`（不加 `--skip-install`）会以 root 身份从 `github.com/XTLS/Xray-install` 下载安装脚本并执行；脚本完整性由上游负责，本命令不做校验。安装步骤前会有交互式确认，CI 场景可加 `--yes`。

### 自动化 runner 的 `RUN_CMD`

`file-change-runner` / `docker-hub-runner` / `cf-tunnel-watcher` 会以 `shell=True` 执行用户传入的命令字符串。`RUN_CMD` 来自命令行参数本身——若你在脚本里拼接外部输入构造 `RUN_CMD`，要自己做转义。

### `agent-bark-notify` 审计日志

`ai-assistant agent-bark-notify hook` 默认不写本地审计日志。需要排查 Codex 或 Claude Code hook 是否被调用、为何跳过或 Bark 发送是否失败时，可以显式启用 JSONL 审计：

```shell
AGENT_BARK_NOTIFY_AUDIT_LOG=1 \
AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=/tmp/agent-bark-notify.log \
ai-assistant agent-bark-notify hook --runtime codex --event completion --dry-run
```

不设置 `AGENT_BARK_NOTIFY_AUDIT_LOG_FILE` 时，默认写入 `~/.ai-assistant/agent-bark-notify.log`。审计记录只包含 runtime、event、状态、项目名、标题、正文长度、session/dedupe 哈希、错误摘要，以及非空 Lody 白名单环境变量；不会写入原始 hook payload、Bark device key、Bark URL、完整通知正文或点击跳转 URL。审计写入失败不会影响通知发送或 hook 退出。

当检测到 Lody 环境时，审计记录会额外包含独立 `lody` 对象；没有任何非空白名单变量时不会写入该字段。`lody` 只包含 `LodySettings` 管理的 `LODY_ELECTRON_BOOTSTRAP`、`LODY_ELECTRON_SESSION_USER_ID`、`LODY_SESSION_ID`、`LODY_WORKSPACE_SESSION_ID`，不会扫描或记录任意 `LODY_*` 变量。`LODY_ELECTRON_SESSION_USER_ID` 也会作为 Lody runtime / identity 自动识别信号。

本地 dry-run 验证显示：通过 shell 启动的 Codex hook 命令可以读取命令环境里的 `AGENT_BARK_NOTIFY_AUDIT_LOG` 和 `AGENT_BARK_NOTIFY_AUDIT_LOG_FILE`。Claude Code hook 命令同样继承父进程环境。若从 GUI 或其他不继承 shell 环境的启动方式运行 agent，建议把审计环境变量写在 hook command、包装脚本或 agent 启动环境中。

Bark `group` 优先使用显式 `BARK_GROUP`。未设置 `BARK_GROUP` 时，默认按 AgentName 分组；可通过 `AGENT_BARK_NOTIFY_GROUP_MODE` 或 hook CLI 的 `--group-mode` 改为 `agent`、`project` 或 `project-branch`，其中 CLI 参数优先于环境变量。`project-branch` 的格式为 `{ProjectName}@{BranchName}`，缺少分支时退化为 ProjectName。

```shell
AGENT_BARK_NOTIFY_GROUP_MODE=project-branch \
ai-assistant agent-bark-notify hook --runtime codex --event completion --dry-run

ai-assistant agent-bark-notify hook --runtime codex --event completion --group-mode project --dry-run
```

通知标题默认格式是 `[{agent}][{event}][{project}][{branch}][{session}]`，不存在的部分会直接省略。可通过 `AGENT_BARK_NOTIFY_TITLE_TEMPLATE` 覆盖，支持 `{agent}`、`{event}`、`{project}`、`{branch}`、`{session}`、`{runtime}`、`{cwd_basename}`，以及 `LodySettings` 管理的 `{LODY_ELECTRON_BOOTSTRAP}`、`{LODY_ELECTRON_SESSION_USER_ID}`、`{LODY_SESSION_ID}`、`{LODY_WORKSPACE_SESSION_ID}`。标题模板中的 Lody 变量不做 URL 编码，但会继续沿用空白规范化逻辑。项目名会优先使用 hook payload 里的 `project_name`、`workspace_name`、`repository`、`repo`、`name`，其次使用 `AGENT_BARK_NOTIFY_PROJECT_NAME`、`CODEX_WORKSPACE_NAME`、`CODEX_PROJECT_NAME`、`LODY_WORKSPACE_NAME`、`LODY_PROJECT_NAME`，最后回退到 `cwd` / `workspace` / `project_path` 的目录名。分支名会优先使用 hook payload / 环境变量中的分支字段，最后基于项目目录执行只读 `git branch --show-current` 探测。

点击通知跳转 URL 可通过 `AGENT_BARK_NOTIFY_HOOK_URL` 设置。设置后，hook 会渲染模板并把结果作为 Bark API 的 `url` 表单字段发送；未设置时不会发送该字段，现有 Bark POST 行为不变。dry-run 输出会在渲染成功时额外包含 `click_url`，其中 `url` 字段仍表示 Bark API endpoint。

```shell
printf '%s' '{"session_id":"s/demo 1","cwd":"/tmp/demo-project"}' \
  | env AGENT_BARK_NOTIFY_HOOK_URL='lody://session/{session_id}' \
      BARK_DEVICE_KEY=device-key \
      ai-assistant agent-bark-notify hook --runtime codex --event completion --dry-run
```

`AGENT_BARK_NOTIFY_HOOK_URL` 支持 `{runtime}`、`{agent}`、`{event}`、`{project}`、`{branch}`、`{session}`、`{session_id}`、`{session_key}`、`{conversation_id}`、`{message_id}`、`{run_id}`、`{agent_id}`、`{workspace_dir}`、`{cwd_basename}`，以及 `{LODY_ELECTRON_BOOTSTRAP}`、`{LODY_ELECTRON_SESSION_USER_ID}`、`{LODY_SESSION_ID}`、`{LODY_WORKSPACE_SESSION_ID}`。变量值会单独 percent-encode，模板静态部分不会整体重新编码；例如 `s/demo 1` 会渲染为 `s%2Fdemo%201`。snake_case 变量会读取对应 camelCase payload 字段，例如 `sessionId`、`sessionKey`、`conversationId`、`messageId`、`runId`、`agentId`、`workspaceDir`。未知变量、格式错误或空渲染结果会被视为非法模板，hook 会省略 click URL 且继续退出 0。

## 开发

```shell
git clone https://github.com/qsoyq/ai-assistant.git
cd ai-assistant
uv sync --all-extras --group dev
uv run pre-commit install
uv run pytest -q
```

启动开销已通过子命令 lazy-load 优化到 ~170ms（`.venv/bin/ai-assistant --help`）。新增子命令时只需在 `ai_assistant/commands/main.py` 的 `LAZY` 字典里加一行 `("name", ("module:cmd", "extra_or_None"))`，无须修改其他位置——root `--help` 的描述列由 AST 从模块顶层 `helptext` 字面量自动抓取。

文档刷新：

```shell
uv run typer --app cmd ai_assistant.commands.main utils docs \
    --name ai-assistant --output docs/COMMANDS.md
```

本地检查：

```shell
uv run pre-commit run --all-files
uv run pytest -q
uv build
```

## 构建与发布

本项目使用 Hatchling 构建 wheel，版本号维护在 `pyproject.toml`。

```shell
uv build
```

发布前需要确认：

- `uv run pre-commit run --all-files` 通过。
- `uv run pytest -q` 通过。
- `uv build` 能生成 wheel/sdist。
- README、`docs/COMMANDS.md` 和版本号已按实际变更更新。

发布到包仓库时使用仓库配置的凭据，不要把 token、密码或 `.pypirc` 提交到仓库。

## 分支与协作

仓库使用 GitHub Flow：

- `main` 是默认分支，保持可发布状态。
- 所有变更通过 issue 跟踪，并从 `main` 创建工作分支。
- PR 必须说明关联 issue、影响范围、验证方式、风险和回滚方案。
- `main` 分支保护期望见 `.github/settings.yml`；平台实际状态以 GitHub Branch Protection / Rulesets 为准。

## 维护与安全

当前维护人：@qsoyq。

安全问题不要提交公开 issue。请按 `SECURITY.md` 进行私下报告，并在确认影响前避免公开复现细节。

本地开发可以复制 `.env.example` 为 `.env`。`.env` 只用于本地，不能提交真实密钥、token、密码、证书或私钥。

### 推荐的渐进 mypy 严格化

当前 `pyproject.toml` 的 mypy 配置较松（仅 `warn_return_any` + `warn_unused_configs`）。建议按下列顺序逐步提严：

```toml
[tool.mypy]
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
explicit_package_bases = true

# 第一阶段：函数签名要求
check_untyped_defs = true
no_implicit_optional = true

# 第二阶段：要求所有公开符号有类型
disallow_untyped_defs = true        # 强制写函数签名类型
disallow_incomplete_defs = true     # 禁止只标注一半

# 第三阶段：更严
warn_unused_ignores = true
warn_redundant_casts = true
strict_equality = true
```

每开一档先在分支上跑 `uv run mypy ai_assistant`，按错误数量决定是分文件 `# type: ignore` 渐进，还是直接补类型。
