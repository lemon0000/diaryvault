# DiaryVault remote access plan

Current state:

- `diaryvault serve` runs a local HTTP API.
- `diaryvault mcp-http` runs a local streamable HTTP MCP server.
- REST defaults to `127.0.0.1:8765`.
- MCP HTTP defaults to `127.0.0.1:8766/mcp`.
- Both are local-only by default.
- Web ChatGPT and other devices cannot call `127.0.0.1` on this computer.

Goal:

- ChatGPT on the web and other devices can access the same DiaryVault knowledge base.

Recommended architecture:

```text
ChatGPT / phone / laptop
        |
        | HTTPS + Bearer token
        v
Public tunnel or HTTPS gateway
        |
        v
DiaryVault API on this Windows PC
        |
        v
DiaryVault\db\diaryvault.sqlite
```

## Route A: Custom GPT Action + HTTPS endpoint

Use this when you want to open a GPT in ChatGPT and ask it to consult your diary memory.

Requirements:

- A reachable HTTPS URL that forwards to `diaryvault serve`.
- Bearer token authentication.
- The OpenAPI schema at `/openapi.json`.

Local command:

```powershell
.\.venv\Scripts\python.exe -m diaryvault serve --vault .\DiaryVault --api-token-file .\.secrets\diaryvault-api-token.txt
```

Then expose it through an HTTPS tunnel or a small VPS reverse proxy.

In the GPT action editor, import:

```text
https://YOUR_DOMAIN_OR_TUNNEL/openapi.json
```

Configure authentication as Bearer API key and paste the token from:

```text
.secrets\diaryvault-api-token.txt
```

## Route B: OpenAI MCP / Plugin connection

Use this when your ChatGPT workspace supports custom MCP apps/plugins.

The MCP adapter is now available locally.

```text
ChatGPT MCP plugin -> HTTPS tunnel -> DiaryVault MCP HTTP -> DiaryVault SQLite
```

Local command:

```powershell
.\scripts\new-diaryvault-api-token.ps1
.\scripts\run-diaryvault-mcp-http.ps1
```

Local MCP endpoint:

```text
http://127.0.0.1:8766/mcp
```

For ChatGPT web, expose that endpoint through Secure MCP Tunnel or an HTTPS tunnel. If using Cloudflare Quick Tunnel for testing:

```powershell
.\scripts\run-diaryvault-mcp-cloudflare-quick-tunnel.ps1
```

Then connect ChatGPT to:

```text
https://YOUR-TUNNEL-HOST/mcp
```

Expected tools:

```text
get_stats
search_diaries
recall_memories
get_diary
get_recent_diaries
```

## Route C: Sync database to cloud

Use this when you need access even when the Windows PC is off.

Tradeoff:

- Availability is better.
- A copy of the diary database leaves the local machine.

I do not recommend this as the default for private diary data.

## Security baseline

- Do not bind `diaryvault serve` to `0.0.0.0` without a token.
- Prefer an HTTPS tunnel or reverse proxy with access control.
- Treat `/diaries/{id}` as sensitive because it returns full diary text.
- Rotate the token if it is pasted into the wrong place.
