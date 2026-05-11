# ai-assistant

个人开发用的 CLI 工具集，一个二进制 + 21 个子命令，覆盖 SSL/网络/存储/RSS/容器/macOS 自动化等日常碎片任务。

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
| `all` | 全部 | 上述并集 |

## ⚠️ 安全提示

### `disable-ssl-verify` / `httpx-disable-verify` / `requests-disable-verify`

这些命令通过 `.pth` 文件**对当前 venv 内的所有 Python 进程**全局禁用 SSL 证书校验，包括用户显式传入 `verify=True` 或自定义 CA bundle 的情况。

- **不要在生产环境使用**——任何 MITM 都会无声放行。
- 仅适合本地调试受信网络中的自签名证书 / 代理抓包等场景。
- 卸载方式：`ai-assistant disable-ssl-verify uninstall`。

### `reality build` 自动安装 xray

`ai-assistant reality build`（不加 `--skip-install`）会以 root 身份从 `github.com/XTLS/Xray-install` 下载安装脚本并执行；脚本完整性由上游负责，本命令不做校验。安装步骤前会有交互式确认，CI 场景可加 `--yes`。

### 自动化 runner 的 `RUN_CMD`

`file-change-runner` / `docker-hub-runner` / `cf-tunnel-watcher` 会以 `shell=True` 执行用户传入的命令字符串。`RUN_CMD` 来自命令行参数本身——若你在脚本里拼接外部输入构造 `RUN_CMD`，要自己做转义。

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
