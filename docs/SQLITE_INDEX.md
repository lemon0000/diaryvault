# DiaryVault SQLite index

Build or rebuild the local SQLite database:

```powershell
.\.venv\Scripts\python.exe -m diaryvault index --vault .\DiaryVault
```

Default output:

```text
DiaryVault\db\diaryvault.sqlite
```

Tables:

- `diaries`: one row per diary entry, including date, title, content, weather, mood, space and raw JSON.
- `images`: one row per known or referenced image id, including whether a local image file exists.
- `diary_images`: many-to-many relation between diary entries and image ids.
- `archive_meta`: index metadata and copied archive metadata.
- `diary_fts`: full-text table when SQLite FTS5 is available.
- `diary_chunks` and `chunk_vectors`: local chunk-level vector index for offline recall.
- `chunk_semantic_vectors`: optional local semantic embeddings keyed by provider/model/text hash.

Useful checks:

```powershell
.\.venv\Scripts\python.exe -m diaryvault index --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault validate --vault .\DiaryVault
```

Search examples:

```powershell
.\.venv\Scripts\python.exe -m diaryvault search "关键词" --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault search "工作" --from 2024-01-01 --to 2024-12-31 --limit 10 --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault search --from 2026-09-01 --limit 20 --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault search "关键词" --json --vault .\DiaryVault
```

Local vector recall:

```powershell
.\.venv\Scripts\python.exe -m diaryvault recall "工作压力" --vault .\DiaryVault --limit 12
.\.venv\Scripts\python.exe -m diaryvault recall "某个长期困扰" --from 2023-01-01 --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault --limit 30 --group-by year
```

Semantic vector indexing:

```powershell
.\.venv\Scripts\python.exe -m diaryvault semantic-index --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault recall "职业方向迷茫" --vault .\DiaryVault --semantic required
```

See `docs/SEMANTIC_RETRIEVAL.md` for the Ollama/BGE-M3 setup.

Stats:

```powershell
.\.venv\Scripts\python.exe -m diaryvault stats --vault .\DiaryVault
.\.venv\Scripts\python.exe -m diaryvault stats --vault .\DiaryVault --write-report
```

Context pack for later RAG/LLM use:

```powershell
.\.venv\Scripts\python.exe -m diaryvault context "某个问题或关键词" --vault .\DiaryVault --limit 12
.\.venv\Scripts\python.exe -m diaryvault context "某个问题或关键词" --vault .\DiaryVault --full --max-chars 1200
```

`context` defaults to local vector recall. Use `--method search` when you need exact keyword search.

Portable ZIP export:

```powershell
.\.venv\Scripts\python.exe -m diaryvault export --vault .\DiaryVault
```

Local memory API:

```powershell
.\.venv\Scripts\python.exe -m diaryvault serve --vault .\DiaryVault
```

See `docs/API.md` for endpoints.

The daily scheduled script now runs:

1. `diaryvault daily --days 14`
2. `diaryvault index`
3. `diaryvault semantic-index --skip-if-unavailable`
4. `diaryvault stats --write-report`
5. `diaryvault validate`
