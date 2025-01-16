"""Read-only installation and workspace diagnostics. Never prints credentials."""
import importlib.util
import json
import os
import shutil
import sys
from .common import file_hash, inside, load_catalog, read_json


def doctor(workspace):
    result = {"python": sys.version.split()[0], "optional_dependencies": {
        name: importlib.util.find_spec(name) is not None
        for name in ("cv2", "whisper", "sklearn", "vaderSentiment", "yt_dlp")},
        "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")),
        "credentials_present": {k: bool(os.environ.get(k)) for k in ("OPENAI_API_KEY", "YOUTUBE_API_KEY")},
        "workspace": str(workspace), "errors": []}
    try:
        cat = load_catalog(workspace)
        cfg = read_json(workspace / "study.json")
        result.update(videos=len(cat), response_mode=cfg.get("response_mode", "direct"), is_demo=cfg.get("is_demo", False))
        for v in cat:
            if not v.get("media_path") or not inside(workspace, v["media_path"]).is_file():
                result["errors"].append("Missing media: " + v["video_id"])
            elif file_hash(inside(workspace, v["media_path"])) != v.get("media_sha256"):
                result["errors"].append("Media hash mismatch: " + v["video_id"])
    except (ValueError, OSError) as exc:
        result["errors"].append(str(exc))
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))
