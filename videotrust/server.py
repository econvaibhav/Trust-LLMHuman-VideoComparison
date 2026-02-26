"""Local research server. Keep behind a hardened HTTPS proxy for any deployment."""
import csv
import hmac
import io
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .common import csv_cell, file_hash, inside, load_catalog, read_json, read_jsonl
from .compare import comparison, interview_agreement
from .storage import Store, StudyError

WEB = Path(__file__).parent / "web"


def create_server(workspace, host="127.0.0.1", port=8000, admin_token="", interview_request=None):
    workspace = Path(workspace).resolve()
    config = read_json(workspace / "study.json")
    catalog = load_catalog(workspace)
    for v in catalog:
        if not v.get("media_path") or not inside(workspace, v["media_path"]).is_file():
            raise ValueError(f"Missing local video: {v['video_id']}. Restore media before serving this catalog.")
        if v.get("media_sha256") != file_hash(inside(workspace, v["media_path"])):
            raise ValueError("Missing/mismatched media hash. Register the correct videos before collecting responses.")
    n = config.get("videos_per_session", len(catalog))
    if type(n) is not int or not 1 <= n <= len(catalog):
        raise ValueError("videos_per_session must be between one and the catalog size")
    if not config.get("consent_version") or not config.get("consent_text"):
        raise ValueError("Provide study consent text and a consent version")
    if len(admin_token) < 16:
        raise ValueError("Admin token must contain at least 16 characters")
    store = Store(workspace, catalog, config)
    mode = config.get("response_mode", "direct")
    if mode not in ("direct", "interview", "paired"):
        raise ValueError("response_mode must be direct, interview or paired")
    interview = None
    if mode in ("interview", "paired"):
        from .interview import Interview
        interview = Interview(store, **({"request": interview_request} if interview_request else {}))
    videos = {r["video_id"]: r for r in catalog}

    def results(query):
        measures = ["direct_rating", "interview_inferred"] if mode == "paired" else ["interview_inferred" if mode == "interview" else "direct_rating"]
        selected_measure = query.get("measure", [measures[0]])[0]
        if selected_measure not in measures:
            raise StudyError("Unknown participant measure", 400)
        analyses = read_jsonl(workspace / "analyses.jsonl")
        participant_rows = store.participant_rows()
        try:
            result = comparison(catalog, participant_rows, analyses,
                                config.get("is_demo", False), query.get("group", [None])[0], selected_measure)
        except ValueError as exc:
            raise StudyError(str(exc), 400) from None
        result["available_measures"] = measures
        result["study"] = {"title": config.get("title", "Video trust study"), "response_mode": mode,
                           "consent_version": config["consent_version"], "videos_per_session": n}
        result["summary"].update(store.progress_summary())
        result["interview_agreement"] = interview_agreement(participant_rows) if mode == "paired" else None
        for row in result["rows"]:
            vid = row["video_id"]
            row["prepared"] = (workspace / "evidence" / (vid + ".json")).exists()
            row["context_ready"] = (workspace / "context" / (vid + ".json")).exists()
            row["response_count"] = sum(r["video_id"] == vid and r["measure"] == selected_measure for r in participant_rows)
        result["summary"]["prepared_videos"] = sum(r["prepared"] for r in result["rows"])
        result["summary"]["model_videos"] = sum(bool(r["model_n"]) for r in result["rows"])
        result["summary"]["participant_videos"] = sum(bool(r["human_n"]) for r in result["rows"])
        return result

    class Handler(BaseHTTPRequestHandler):
        server_version = "VideoTrust"

        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, fmt, *args):
            pass  # Avoid recording participant IP addresses or authorization data.

        def headers_common(self):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")

        def send(self, status, data, content_type="application/json; charset=utf-8", attachment=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.headers_common()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def auth(self, admin=False):
            header = self.headers.get("Authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            if not token or (admin and not hmac.compare_digest(token, admin_token)):
                raise StudyError("Enter a valid access token.", 401)
            return token

        def body(self):
            origin = self.headers.get("Origin")
            # Browser requests must be same-origin. CLI requests have no Origin.
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                raise StudyError("Cross-origin requests are not allowed.", 403)
            if self.headers.get_content_type() != "application/json":
                raise StudyError("Send JSON data.", 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise StudyError("Invalid content length.")
            if not 0 < size <= 16384:
                raise StudyError("Request body is empty or too large.", 413)
            try:
                value = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeDecodeError):
                raise StudyError("Invalid JSON.")
            if not isinstance(value, dict):
                raise StudyError("JSON body must be an object.")
            return value

        def media(self, vid):
            if vid not in videos:
                raise StudyError("Video not found.", 404)
            path = inside(workspace, videos[vid]["media_path"])
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            range_header = self.headers.get("Range")
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
                if not match or not any(match.groups()):
                    return self.bad_range(size)
                lo, hi = match.groups()
                if lo:
                    start, end = int(lo), min(int(hi), size - 1) if hi else size - 1
                else:
                    start, end = max(0, size - int(hi)), size - 1
                if start > end or start >= size:
                    return self.bad_range(size)
                status = 206
            self.send_response(status)
            self.headers_common()
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            with path.open("rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def bad_range(self, size):
            self.send_response(416)
            self.headers_common()
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                parsed = urlsplit(self.path)
                path = parsed.path
                if path == "/api/health":
                    return self.send(200, {"status": "ok"})
                if path == "/api/study":
                    return self.send(200, {k: config.get(k) for k in ("title", "consent_text", "consent_version", "is_demo", "videos_per_session", "contact", "response_mode")})
                if path == "/api/session":
                    return self.send(200, store.current(self.auth()))
                if path == "/api/admin/comparison":
                    self.auth(True)
                    return self.send(200, results(parse_qs(parsed.query)))
                if path == "/api/admin/comparison.csv":
                    self.auth(True)
                    result = results(parse_qs(parsed.query))
                    fields = ["video_id", "title", "participant_measure", "condition_id", "human_n", "human_mean", "human_sd", "model_n", "model_mean", "model_sd", "gap"]
                    out = io.StringIO(newline="")
                    writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader()
                    for row in result["rows"]:
                        row = {**row, "participant_measure": result["participant_measure"], "condition_id": result["selected_group"]}
                        writer.writerow({k: csv_cell(row.get(k)) for k in fields})
                    return self.send(200, out.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "comparison.csv")
                if path in ("/api/admin/video", "/api/admin/frame"):
                    self.auth(True)
                    query = parse_qs(parsed.query)
                    vid = query.get("id", [""])[0]
                    if vid not in videos:
                        raise StudyError("Video not found", 404)
                    ep = workspace / "evidence" / (vid + ".json")
                    evidence = read_json(ep) if ep.exists() else None
                    if path.endswith("/frame"):
                        try:
                            index = int(query.get("index", [""])[0])
                            if index < 0: raise ValueError()
                            frame = evidence["frames"][index]
                            frame_path = inside(workspace, frame["path"])
                            if file_hash(frame_path) != frame["sha256"]: raise ValueError()
                        except (TypeError, KeyError, IndexError, ValueError, OSError):
                            raise StudyError("Frame not available", 404) from None
                        return self.send(200, frame_path.read_bytes(), "image/jpeg")
                    if evidence:
                        evidence = {**evidence, "frames": [{"timestamp_seconds": f["timestamp_seconds"], "url": f"/api/admin/frame?id={vid}&index={i}"} for i, f in enumerate(evidence["frames"])]}
                    cp = workspace / "context" / (vid + ".json")
                    return self.send(200, {"video_id": vid, "title": videos[vid]["title"], "media_url": "/media/" + vid,
                        "media_info": videos[vid].get("media_info"), "evidence": evidence,
                        "context": read_json(cp) if cp.exists() else None,
                        "participant_responses": [r for r in store.participant_rows() if r["video_id"] == vid],
                        "interview_turns": [r for r in store.interview_export() if r["video_id"] == vid]})
                if path == "/api/admin/interviews.json":
                    self.auth(True)
                    return self.send(200, {"turns": store.interview_export(), "assessments": store.participant_rows()}, attachment="interviews.json")
                if path == "/api/admin/export.csv":
                    self.auth(True)
                    rows = store.participant_rows()
                    fields = sorted({k for row in rows for k in row}) if rows else ["session_id", "video_id", "trust_score", "measure"]
                    out = io.StringIO(newline="")
                    writer = csv.DictWriter(out, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows({k: csv_cell(v) for k, v in row.items()} for row in rows)
                    return self.send(200, out.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "human_responses.csv")
                if path.startswith("/media/"):
                    return self.media(path.removeprefix("/media/"))
                files = {"/": "index.html", "/researcher": "researcher.html", "/app.js": "app.js",
                         "/researcher.js": "researcher.js", "/styles.css": "styles.css"}
                if path in files:
                    f = WEB / files[path]
                    return self.send(200, f.read_bytes(), (mimetypes.guess_type(f.name)[0] or "text/plain") + "; charset=utf-8")
                raise StudyError("Not found.", 404)
            except StudyError as exc:
                self.send(exc.status, {"error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(500, {"error": "Server error. Check the study files and restart."})

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
                if path == "/api/sessions":
                    return self.send(201, store.create(self.body().get("consent")))
                if path == "/api/ratings":
                    token = self.auth()
                    return self.send(200, store.rate(token, self.body()))
                if path in ("/api/interview/answer", "/api/interview/finish") and interview:
                    token = self.auth()
                    return self.send(200, interview.answer(token, self.body(), finish=path.endswith("/finish")))
                raise StudyError("Not found.", 404)
            except StudyError as exc:
                self.send(exc.status, {"error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send(500, {"error": "Response was not confirmed. Retry with the same answers."})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.store = store
    return server
