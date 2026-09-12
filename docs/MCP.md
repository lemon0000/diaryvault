# DiaryVault MCP

DiaryVault exposes a read-only MCP server for local Codex-compatible clients and for later ChatGPT web access through streamable HTTP.

Current tools:

- `get_stats()`
- `search_diaries(query, start_date=None, end_date=None, top_k=10)`
- `recall_memories(query, start_date=None, end_date=None, top_k=10, group_by=None)`
- `get_diary(diary_id, max_chars=5000)`
- `get_recent_diaries(days=7)`

The MCP server reuses the same SQLite retrieval code as the REST API. It does not implement a second search stack.

Set `group_by="year"` on `recall_memories` when you want time-aware recall. The normal flat `results` list is still returned, and an additional `groups` array organizes the same results by year.

## Install MCP support

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
```

## Local stdio MCP

```powershell
.\.venv\Scripts\python.exe -m diaryvault mcp --vault .\DiaryVault
```

This process uses stdio. It should appear to hang because it is waiting for an MCP host to send protocol messages. Do not print logs to stdout from this process.

## Local streamable HTTP MCP

Run the HTTP MCP server on localhost:

```powershell
.\.venv\Scripts\python.exe -m diaryvault mcp-http --vault .\DiaryVault --host 127.0.0.1 --port 8766 --path /mcp
```

Default local endpoint:

```text
http://127.0.0.1:8766/mcp
```

The helper script starts the same server with Bearer token protection:

```powershell
.\scripts\new-diaryvault-api-token.ps1
.\scripts\run-diaryvault-mcp-http.ps1
```

The token is stored at:

```text
.secrets\diaryvault-api-token.txt
```

Do not paste this token into chat logs.

If binding outside localhost, a token is mandatory:

```powershell
.\.venv\Scripts\python.exe -m diaryvault mcp-http --vault .\DiaryVault --host 0.0.0.0 --api-token-file .\.secrets\diaryvault-api-token.txt
```

## Cloudflare Quick Tunnel for testing

Start the local MCP HTTP server first:

```powershell
.\scripts\run-diaryvault-mcp-http.ps1
```

In a second PowerShell window:

```powershell
.\scripts\run-diaryvault-mcp-cloudflare-quick-tunnel.ps1
```

The tunnel prints a public URL. Use the `/mcp` path:

```text
https://YOUR-RANDOM-SUBDOMAIN.trycloudflare.com/mcp
```

The script sets Cloudflare's origin Host header to `127.0.0.1:8766`, so the MCP server's Host header protection remains enabled.

This route is useful for external MCP client testing. It is not the preferred ChatGPT web route for this private diary vault because ChatGPT does not support arbitrary custom API keys; for authenticated public MCP servers, OpenAI expects OAuth-based authorization.

## OpenAI Secure MCP Tunnel for ChatGPT web

For ChatGPT web, prefer OpenAI Secure MCP Tunnel:

```text
ChatGPT
  -> OpenAI control plane
  -> tunnel-client on this Windows machine
  -> http://127.0.0.1:8767/mcp
  -> DiaryVault SQLite
```

The local MCP listener for this route is loopback-only and intentionally has no static token. Do not expose port `8767` through generic public tunnels.

The OpenAI tunnel client is installed locally at:

```text
.tools\tunnel-client\tunnel-client.exe
```

Create or inspect the tunnel and runtime key in OpenAI's settings:

- Tunnels: <https://platform.openai.com/settings/organization/tunnels>
- Runtime API keys: <https://platform.openai.com/settings/organization/api-keys>
- ChatGPT connector settings: <https://chatgpt.com/#settings/Connectors>

The runtime key used by the long-running tunnel daemon needs Tunnels Read + Use. Do not use an admin key for the long-running daemon.

Start the local MCP server for the OpenAI tunnel in one PowerShell window:

```powershell
.\scripts\run-diaryvault-mcp-http-openai-tunnel.ps1
```

Initialize the tunnel profile after you have a `tunnel_...` ID:

```powershell
.\scripts\init-diaryvault-openai-tunnel.ps1 -TunnelId tunnel_... -Force
```

Provide the runtime API key without printing it in chat logs. Either set it in the current PowerShell process:

```powershell
$env:CONTROL_PLANE_API_KEY = "YOUR_RUNTIME_KEY"
```

Or save it to this gitignored file:

```text
.secrets\openai-control-plane-api-key.txt
```

Then run the tunnel in a second PowerShell window:

```powershell
.\scripts\run-diaryvault-openai-tunnel.ps1
```

While `tunnel-client` is running, open ChatGPT connector settings and add the tunnel-backed MCP connection. Keep both the local MCP HTTP process and `tunnel-client` running for connector discovery and every later MCP call.

## Codex project config

This repo does not track machine-specific Codex config because it contains absolute local paths. Copy the example config and adjust it for your machine:

```text
examples\codex-config.toml
```

Equivalent configuration:

```toml
[mcp_servers.diaryvault]
command = 'C:\path\to\Diary\.venv\Scripts\python.exe'
args = ['-m', 'diaryvault', 'mcp', '--vault', 'C:\path\to\Diary\DiaryVault']
cwd = 'C:\path\to\Diary'
startup_timeout_sec = 20
tool_timeout_sec = 60
```

Keep the real `.codex\config.toml` local and gitignored.

After restarting a Codex client that reads project-scoped MCP config, the expected tools are:

```text
diaryvault.get_stats
diaryvault.search_diaries
diaryvault.recall_memories
diaryvault.get_diary
diaryvault.get_recent_diaries
```

Example time-aware MCP call:

```text
recall_memories(
  query="职业选择、未来方向、工作还是读研的不确定感",
  top_k=30,
  group_by="year"
)
```

## Safety constraints

- MCP tools are read-only.
- There are no delete/update tools.
- There is no SQL execution tool.
- There is no filesystem read tool.
- `get_diary` caps `max_chars` at 10000.
- `search_diaries` and `recall_memories` cap `top_k` at 50.

## Local validation result

Validated against a populated local vault on 2026-09-10:

```text
tools get_stats,search_diaries,recall_memories,get_diary,get_recent_diaries
```

`recall_memories` automatically uses `hybrid-vector` after semantic vectors are built and the local embedding provider is reachable. Until then it keeps using the existing `local-vector` retrieval.

Chinese query validation should be run through a UTF-8 MCP host. PowerShell code-page conversions can corrupt direct Chinese text passed through ad-hoc shell pipes.

## ChatGPT web

ChatGPT web does not read local Codex config files. Per official OpenAI documentation, ChatGPT web uses remote MCP-backed tools supplied by plugins, while local Codex clients can connect directly to stdio MCP servers.

For ChatGPT web:

```text
DiaryVault MCP server
  -> streamable HTTP http://127.0.0.1:8766/mcp
  -> public HTTPS endpoint or Secure MCP Tunnel
  -> ChatGPT plugin connection
```

OpenAI's documented connection flow:

1. Open ChatGPT Settings.
2. Select Security and login.
3. Enable Developer mode.
4. Go to ChatGPT Plugins.
5. Add an MCP server.
6. Enter the HTTPS endpoint including `/mcp`.
7. Review discovered tools.
8. Start a new conversation and enable the MCP connection from the tools menu.

For private diary data, prefer Secure MCP Tunnel or a tunnel protected by strong authentication. Do not expose this diary MCP server publicly without HTTPS, token/auth, logging, and rate limiting.

References:

- <https://developers.openai.com/plugins/deploy/connect-chatgpt>
- <https://developers.openai.com/plugins/concepts/mcp-server>
- <https://developers.openai.com/plugins/build/authenticate-users>
- <https://developers.openai.com/api/docs/guides/secure-mcp-tunnels>
- <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/origin-parameters/>
