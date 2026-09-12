# DiaryVault memory API

Run the local API:

```powershell
.\.venv\Scripts\python.exe -m diaryvault serve --vault .\DiaryVault
```

Default address:

```text
http://127.0.0.1:8765
```

The server is local-only by default. If you bind it outside localhost, set an API token:

```powershell
$env:DIARYVAULT_API_TOKEN = "your-long-random-token"
.\.venv\Scripts\python.exe -m diaryvault serve --vault .\DiaryVault --host 0.0.0.0
```

When a token is configured, send:

```text
Authorization: Bearer <your-token>
```

Endpoints:

```text
GET /health
GET /openapi.json
GET /stats
GET /search?q=关键词&from=2024-01-01&to=2024-12-31&limit=20&order=newest
GET /recall?q=工作压力&from=2023-01-01&limit=12
GET /recall?q=职业方向迷茫&limit=30&group_by=year
GET /context?q=某个问题&limit=12&full=false&method=recall
GET /diaries/{diary_id}
```

Examples:

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/health"
Invoke-RestMethod "http://127.0.0.1:8765/openapi.json"
Invoke-RestMethod "http://127.0.0.1:8765/search?q=工作&limit=5"
Invoke-RestMethod "http://127.0.0.1:8765/recall?q=工作压力&limit=5"
Invoke-RestMethod "http://127.0.0.1:8765/recall?q=职业方向迷茫&limit=30&group_by=year"
Invoke-RestMethod "http://127.0.0.1:8765/context?q=我过去几年反复提到的困扰是什么&limit=12"
```

Notes:

- The API reads from `DiaryVault\db\diaryvault.sqlite`.
- It does not call external APIs.
- `/recall` supports `group_by=year` and returns both flat `results` and grouped `groups`.
- `/context` returns a context pack in JSON and does not write report files.
- `/diaries/{diary_id}` returns full local diary content; keep the service local unless you have configured a token.
