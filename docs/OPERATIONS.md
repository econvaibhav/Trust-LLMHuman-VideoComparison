# Running and looking after a study

## Local demo

Run `python -m videotrust demo`. It copies bundled fictional clips and synthetic model fixtures into a new workspace, then serves the real collector. Repeating it resumes the same workspace. To get a fresh demo, supply a new path, for example `--workspace data/demo2`.

Only the survey/demo server uses the Python standard library. Optional analysis/collection dependencies are installed explicitly. The demos make no paid requests. A real interview study makes model requests when participants answer or finish; the direct-rating server does not. Collection and video assessment run as separate commands.

The printed researcher token unlocks aggregate results and CSV downloads. Set `VIDEOTRUST_ADMIN_TOKEN` to a strong random value of at least 16 characters if you want a stable token across restarts. Otherwise the process generates a fresh one. The researcher page keeps it in memory rather than in a URL.

Participant bearer tokens are kept in the browser tab's session storage and stored only as hashes server-side. Reloading the tab resumes the session. Clearing session storage or using a new browser/tab can start another participant session; there is no account-level duplicate-person detection.

## Data lifecycle

| File | Meaning |
|---|---|
| `catalog.json` | Stable video identities, titles, metadata, and media paths/hashes |
| `study.json` | Consent wording/version, contact, sample length and demo/research mode |
| `responses.sqlite3` | Sessions, random order, exposure timestamps, direct ratings, interview turns and inferred assessments |
| `evidence/*.json` | Transcript/segments, language, duration and frame paths/hashes |
| `frames/` | Sampled JPEG evidence |
| `context/`, `topics.json` | Visual summaries, format, sentiment and corpus-level topic clusters |
| `enrichment_report.json` | Context preparation and topic errors |
| `analyses.jsonl` | Successful model judgments with provenance and raw output |
| `analysis_errors.jsonl` | Failed jobs, available for retry/review |
| `preparation_report.json` | Prepared/failed video IDs |
| `registration_report.json` | Validated local clips and rejected files |
| `collection_report.json` | Collection counts and failures |
| `legacy_analyses.jsonl` | Historical imports, separated from prospective results |
| `comparison.json`, `comparison.csv` | Exported comparisons, separated by model condition |

Keep these workspaces out of Git. The project `.gitignore` excludes the default `data/` location, `.env`, database files and common private folders. If you place raw data elsewhere, add that location to `.gitignore` yourself. Do not place private files in `videotrust/demo/`, which is intentionally tracked.

Before changing a study catalog or configuration after collection starts, create a new workspace. The server rejects changes that would silently alter the interpretation of existing rows. Analyze the registered bytes; do not replace videos in a running study. Model results with mismatched media hashes are excluded from comparisons.

Run at most one preparation/enrichment/analysis writer per workspace. JSONL append and completion tracking support interrupted sequential batches, not distributed scheduling. A damaged final JSONL line is reported rather than silently ignored; repair it from backup before resuming.

## Backup and export

Use the dashboard's **Export responses** button for CSV. Spreadsheet formula-leading text is escaped; verbatim user text remains in SQLite. For an exact database backup while the server is running, use SQLite's backup API rather than copying only the main file while WAL writes are active:

```python
import sqlite3
with sqlite3.connect('data/study/responses.sqlite3') as source:
    with sqlite3.connect('responses-backup.sqlite3') as backup:
        source.backup(backup)
```

Keep the consent/config, catalog, media, evidence and analysis files alongside the backup. Retention and withdrawal procedures must be defined for your study. The local app does not implement automatic deletion or a participant withdrawal portal.

## Public hosting

The included `ThreadingHTTPServer` is a dependency-free local reference implementation. It is not a hardened public study service. Before deployment, use HTTPS and a hardened reverse proxy/service, restrict researcher access, apply resource/rate limits, test concurrent load, configure backups and review study consent. The UI/API are same-origin; there is no permissive CORS setting. The server does not log participant IP addresses, but your host/proxy may do so.

Media endpoints are public within the local service; the admin token protects results, not participant access or the media catalog. There is no recruitment token, bot prevention, external identity provider, automated quota enforcement or fine-grained staff authorization. Those would be separate deployment work.

The included Dockerfile starts the **demo**, without analysis dependencies:

```bash
docker build -t video-trust-lab .
docker run --rm -p 127.0.0.1:8000:8000 -v video-trust-data:/data video-trust-lab
```

The named volume persists responses. For a real study, mount a prepared workspace with readable media and writable database storage, supply a stable admin token through the runtime environment, and override the command with `python -m videotrust serve --workspace /data/study --host 0.0.0.0`. Container build/deployment was not exercised in local verification.

## Troubleshooting

| Symptom | Check |
|---|---|
| Python cannot find `videotrust` | Run from the repository root, or install with `pip install -e .` |
| Blank/unplayable video | Restore the correct media; use browser-compatible H.264 MP4; check `ffprobe` |
| Study refuses to start after edits | Catalog/config was frozen when the database was created; use a new workspace |
| Model condition missing | Check successful `analyses.jsonl` rows, media hashes and `analysis_errors.jsonl` |
| OpenCV/Whisper import error | Install the `analysis` extras in the interpreter you are running |
| FFmpeg/ffprobe missing | Install the operating-system FFmpeg package and make it available on PATH |
| API 401/403/429 | Verify credentials, model access and quota; rotate any exposed old keys |
| Researcher token rejected | Use the token from the currently running process |
| Legacy media restore incomplete | Check exact original filenames and duplicates in `media_restore_report.json` |

## Interview operation

Set `response_mode` to `interview` or `paired` before starting a new study. Live interviews need `OPENAI_API_KEY`; the demo uses fixed scripted fixtures. One local server process owns the workspace. Only overlapping requests from the same session are rejected with a retry message. Different sessions can call the provider concurrently. This is appropriate for local testing, not a high-concurrency recruitment service.

Answers are saved before follow-up generation. A failed follow-up exposes **Retry follow-up question** or **Finish interview**. A failed final assessment also leaves answers saved; choose **Finish interview** to retry. Draft ratings and text survive reloads in the same tab, and a media playback error disables both response forms. Participant pages never receive inferred or video-based scores. Authorized researchers can export conversations with the **Export interviews** button. Include the transfer of live participant text to the model provider in your study information.
