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
| `all` | 全部 | 上述并集 |

## ⚠️ 安全提示

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
AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG=1 \
AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=/tmp/agent-bark-notify.log \
ai-assistant agent-bark-notify hook --runtime codex --event completion --dry-run
```

不设置 `AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE` 时，默认写入 `~/.ai-assistant/agent-bark-notify.log`。审计记录只包含 runtime、event、状态、项目名、标题、正文长度、session/dedupe 哈希和错误摘要；不会写入原始 hook payload、Bark device key、Bark URL 或完整通知正文。审计写入失败不会影响通知发送或 hook 退出。

本地 dry-run 验证显示：通过 shell 启动的 Codex hook 命令可以读取命令环境里的 `AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG` 和 `AI_ASSISTANT_AGENT_BARK_NOTIFY_AUDIT_LOG_FILE`。Claude Code hook 命令同样继承父进程环境。若从 GUI 或其他不继承 shell 环境的启动方式运行 agent，建议把审计环境变量写在 hook command、包装脚本或 agent 启动环境中。

通知标题默认格式是 `[{agent}][{event}][{project}][{branch}][{session}]`，不存在的部分会直接省略。可通过 `AI_ASSISTANT_AGENT_BARK_NOTIFY_TITLE_TEMPLATE` 覆盖，支持 `{agent}`、`{event}`、`{project}`、`{branch}`、`{session}`、`{runtime}`、`{cwd_basename}`。项目名会优先使用 hook payload 里的 `project_name`、`workspace_name`、`repository`、`repo`、`name`，其次使用 `AI_ASSISTANT_AGENT_BARK_NOTIFY_PROJECT_NAME`、`CODEX_WORKSPACE_NAME`、`CODEX_PROJECT_NAME`、`LODY_WORKSPACE_NAME`、`LODY_PROJECT_NAME`，最后回退到 `cwd` / `workspace` / `project_path` 的目录名。分支名会优先使用 hook payload / 环境变量中的分支字段，最后基于项目目录执行只读 `git branch --show-current` 探测。

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
