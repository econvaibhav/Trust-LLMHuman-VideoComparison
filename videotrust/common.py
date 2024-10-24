"""Small, dependency-free building blocks shared by the application and pipeline."""
import hashlib
import json
import math
import os
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def legacy_id(filename):
    # Exact normalized filename identity; never fuzzy-match two similar titles.
    return "legacy_" + digest(unicodedata.normalize("NFC", filename))[:24]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as f:
        tmp = Path(f.name)
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    os.replace(tmp, path)


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    if not Path(path).exists():
        return []
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Malformed JSONL at line {n} of {Path(path).name}") from exc
    return rows


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path leaves the workspace")
    return path


def load_catalog(workspace):
    rows = read_json(Path(workspace) / "catalog.json")
    if not isinstance(rows, list) or not rows:
        raise ValueError("catalog.json must contain a nonempty list")
    seen = set()
    for row in rows:
        vid = row.get("video_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", vid) or vid in seen:
            raise ValueError("Video IDs must be unique, nonempty and URL-safe")
        seen.add(vid)
        if not isinstance(row.get("title"), str) or not row["title"].strip():
            raise ValueError(f"Missing title for {vid}")
        if row.get("media_path"):
            inside(workspace, row["media_path"])
    return rows


def finite_number(value, lo, hi):
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


def json_request(url, payload=None, headers=None, attempts=3):
    """Bounded retries; errors omit URLs, which can contain API keys."""
    body = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
    hdr = {"Content-Type": "application/json", **(headers or {})}
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=body, headers=hdr)
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise RuntimeError(f"Remote service returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise RuntimeError("Remote service timed out or was unreachable") from None
        time.sleep(min(2 ** attempt, 4))


def csv_cell(value):
    # Prevent text being interpreted as spreadsheet formulas on CSV opening.
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
