# DiaryVault

DiaryVault 是一个面向“你记（Nideriji）”的本地优先日记归档与个人记忆检索项目。它把用户自己的日记同步或导入到本机，建立 SQLite 索引，并通过 REST API 与 MCP 提供只读检索能力，让 Codex、ChatGPT 或其他 AI 工具可以按需读取相关记忆。

“你记”官网：[https://nideriji.cn/w/](https://nideriji.cn/w/)

> DiaryVault 是个人/社区辅助项目，不是“你记”的官方项目，也不替代“你记”官网或客户端。它只处理用户自己授权导出或同步到本机的数据。

## 项目目标

很多日记应用适合记录，但不一定适合长期归档、全文检索、语义检索和 AI 记忆调用。DiaryVault 想解决的是：

- 把自己的“你记”日记保存成可备份、可校验、可迁移的本地资料。
- 在本机建立 SQLite、全文检索、向量检索和混合检索索引。
- 通过只读 API / MCP，把个人日记变成可控的个人记忆库。
- 尽量保证隐私：默认本地运行，真实日记、图片、数据库和密钥不进入 Git。

## 当前状态

- 主要在 Windows + Python 3.11+ 环境下开发和测试。
- 支持“你记”同步和浏览器扩展 ZIP 导入。
- 支持 SQLite 索引、FTS、n-gram lexical vectors、本地 Ollama semantic vectors。
- 支持 REST API、MCP stdio、MCP streamable HTTP。
- 支持 Windows Scheduled Task 每日自动同步。
- 当前仓库不包含任何真实日记数据。
- License 暂未选择；如果准备正式开源，建议先添加明确许可证。

## 隐私边界

这个仓库应该只包含代码、脚本、测试和文档。以下内容默认被 `.gitignore` 排除：

```text
DiaryVault/    # 本地日记、图片、SQLite 数据库、日志、备份
.secrets/      # 账号、密码、token、tunnel runtime key
.tools/        # 本地下载的 tunnel-client/cloudflared 等工具
.venv/         # Python 虚拟环境
.codex/        # 本机 Codex MCP 配置
.vscode/       # 本机编辑器配置
```

MCP 和 REST API 都按只读边界设计，不提供删除日记、修改日记、执行 SQL、执行命令或任意读取文件的工具。

## 架构概览

```text
你记 / Nideriji
      |
      | sync 或 ZIP import
      v
DiaryVault local archive
      |
      +--> Markdown / images / validation reports
      |
      v
SQLite
      |
      +--> FTS keyword search
      +--> 512-d n-gram lexical vectors
      +--> optional Ollama semantic vectors
      |
      v
Hybrid retrieval
      |
      +--> CLI
      +--> REST API
      +--> MCP stdio / HTTP
```

## 功能

- 日记同步：从“你记”拉取自己的日记。
- ZIP 导入：导入 `nideriji-archive-studio` 导出的归档 ZIP。
- Markdown 导出：按年份生成本地 Markdown 日记文件。
- 图片归档：保存日记引用的图片。
- 离线校验：校验日记数量、图片引用、归档结构等。
- SQLite 索引：建立结构化日记库。
- 关键词检索：基于 SQLite FTS 和字段过滤。
- 本地 lexical vector recall：使用 n-gram hashing vectors，无需外部服务。
- 本地 semantic retrieval：可选通过 Ollama `bge-m3` 生成语义向量。
- Hybrid retrieval：语义向量可用时自动融合 lexical + semantic 结果。
- REST API：提供 `/stats`、`/search`、`/recall`、`/context`、`/diaries/{id}`。
- MCP：提供 `get_stats`、`search_diaries`、`recall_memories`、`get_diary`、`get_recent_diaries`。
- 每日自动同步：默认每天刷新最近 14 天日记并更新索引。

## 安装

```powershell
git clone https://github.com/lemon0000/diaryvault.git
cd diaryvault

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[privacy,mcp]"
```

如果只需要基础同步和检索，也可以先安装核心包：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## 快速开始

初始化本地 vault：

```powershell
.\.venv\Scripts\python.exe -m diaryvault init --vault .\DiaryVault
```

创建本地密钥文件：

```text
.secrets\nideriji.env
```

内容可以参考 [.env.example](.env.example)：

```text
NIDERIJI_EMAIL=you@example.com
NIDERIJI_PASSWORD=replace_me
```

先同步少量样本并校验：

```powershell
.\.venv\Scripts\python.exe -m diaryvault sample --vault .\DiaryVault --mode mine --limit 10 --secrets-file .\.secrets\nideriji.env
.\.venv\Scripts\python.exe -m diaryvault validate --vault .\DiaryVault
```

确认无误后全量同步并建立索引：

```powershell
.\.venv\Scripts\python.exe -m diaryvault sync --vault .\DiaryVault --mode mine --secrets-file .\.secrets\nideriji.env
.\.venv\Scripts\python.exe -m diaryvault index --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault stats --vault .\DiaryVault
```

## 从 ZIP 导入

如果已经通过浏览器扩展导出了 ZIP：

```powershell
.\.venv\Scripts\python.exe -m diaryvault import-zip ".\path\to\NiderijiArchive.zip" --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault index --vault .\DiaryVault
```

## 检索示例

关键词检索：

```powershell
.\.venv\Scripts\python.exe -m diaryvault search "工作" --vault .\DiaryVault --limit 10
```

面向 AI 记忆调用的 recall：

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "我过去有没有出现过类似的职业迷茫？" --vault .\DiaryVault --limit 10
```

按年份组织 recall 结果：

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault --limit 30 --group-by year
```

生成上下文包：

```powershell
.\.venv\Scripts\python.exe -m diaryvault context "最近反复出现的压力来源是什么？" --vault .\DiaryVault --limit 12
```

## Semantic / Hybrid retrieval

Semantic retrieval 默认走本机 Ollama，不把日记正文上传到第三方 embedding 服务。

```powershell
ollama pull bge-m3
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault
```

构建完成后，`recall` 和 MCP `recall_memories` 会在 semantic provider 可用时自动使用 hybrid retrieval；如果 Ollama 暂时不可用，会回退到 lexical retrieval。

## REST API

生成本地 API token：

```powershell
.\scripts\new-diaryvault-api-token.ps1
```

启动本地 REST API：

```powershell
.\scripts\run-diaryvault-api.ps1
```

默认地址：

```text
http://127.0.0.1:8765
```

主要端点：

```text
GET /health
GET /stats
GET /search?q=关键词&limit=10
GET /recall?q=工作压力&limit=10
GET /recall?q=职业方向迷茫&limit=30&group_by=year
GET /context?q=某个问题&limit=12
GET /diaries/{diary_id}
```

更多说明见 [docs/API.md](docs/API.md)。

## MCP

本地 stdio MCP：

```powershell
.\.venv\Scripts\python.exe -m diaryvault mcp --vault .\DiaryVault
```

本地 streamable HTTP MCP：

```powershell
.\scripts\run-diaryvault-mcp-http.ps1
```

当前 MCP 工具：

```text
get_stats
search_diaries
recall_memories
get_diary
get_recent_diaries
```

`recall_memories` 支持 `group_by="year"`，适合让 AI 按年份分析长期变化。

Codex 的本机配置示例见 [examples/codex-config.toml](examples/codex-config.toml)。真实 `.codex/config.toml` 通常包含本机绝对路径，应保持本地私有。

更多说明见 [docs/MCP.md](docs/MCP.md)。

## 每日自动同步

注册 Windows Scheduled Task：

```powershell
.\scripts\register-diaryvault-daily-task.ps1
```

默认每天 03:00 执行：

1. 同步最近 14 天日记。
2. 重建 SQLite 索引。
3. 在 Ollama 可用时刷新 semantic vectors。
4. 写入 stats report。
5. 运行 vault 校验。

更多说明见 [docs/SCHEDULED_SYNC.md](docs/SCHEDULED_SYNC.md)。

## 项目结构

```text
src/diaryvault/
  archive.py       # local archive model and file layout
  client.py        # Nideriji client
  cli.py           # command-line interface
  index.py         # SQLite index builder
  search.py        # keyword/date search
  recall.py        # lexical / semantic / hybrid recall
  semantic.py      # Ollama semantic embedding support
  api.py           # REST API
  mcp_server.py    # MCP stdio and HTTP server

tests/             # unit tests
scripts/           # Windows helper scripts
docs/              # detailed operation docs
examples/          # safe example configs
```

## 开源前检查

正式公开仓库前建议运行：

```powershell
git status --short --ignored
rg --hidden --glob '!.git/**' --glob '!DiaryVault/**' --glob '!.secrets/**' --glob '!.tools/**' --glob '!.venv/**' "sk-[A-Za-z0-9]|tunnel_[A-Za-z0-9]+|Bearer [A-Za-z0-9_-]{20,}"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

如果曾经把敏感文件提交进 Git 历史，仅从当前版本删除是不够的，需要清理 Git history 后再公开。

## Roadmap

- 更完善的增量同步和旧日记变更检测。
- 更强的时间感知检索，例如按年份或阶段组织回忆。
- Life Model：从原始日记派生长期人物、事件、关系、价值观和当前状态。
- 更完整的远程 MCP 安全方案。
- 跨平台脚本支持。

## License

DiaryVault is released under the [MIT License](LICENSE).

## Documentation

- [docs/API.md](docs/API.md)
- [docs/MCP.md](docs/MCP.md)
- [docs/SCHEDULED_SYNC.md](docs/SCHEDULED_SYNC.md)
- [docs/SEMANTIC_RETRIEVAL.md](docs/SEMANTIC_RETRIEVAL.md)
- [docs/SQLITE_INDEX.md](docs/SQLITE_INDEX.md)
- [SECURITY.md](SECURITY.md)
