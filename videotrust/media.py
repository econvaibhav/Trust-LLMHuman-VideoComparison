"""OpenCV frame sampling and local Whisper transcription, loaded only when used."""
import json
import math
import shutil
import subprocess
from pathlib import Path
from .common import file_hash, inside, load_catalog, read_json, write_json


def probe(path):
    if not shutil.which("ffprobe"):
        raise RuntimeError("Install FFmpeg (including ffprobe) to prepare real videos.")
    run = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise ValueError("Video metadata could not be read; the file may be incomplete or damaged")
    return json.loads(run.stdout)


def inspect_media(path):
    """Check container, browser-compatible codecs, duration and decodable video."""
    meta = probe(path)
    videos = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise ValueError("The file has no video stream")
    v = videos[0]
    duration = float(meta.get("format", {}).get("duration", v.get("duration", 0)))
    if not math.isfinite(duration) or duration <= 0 or not v.get("width") or not v.get("height"):
        raise ValueError("Invalid video dimensions or duration")
    suffix = Path(path).suffix.lower()
    audio = [s for s in meta["streams"] if s.get("codec_type") == "audio"]
    if not ((suffix == ".mp4" and v.get("codec_name") == "h264" and
             v.get("pix_fmt") in ("yuv420p", "yuvj420p") and
             all(s.get("codec_name") in ("aac", "mp3") for s in audio)) or
            (suffix == ".webm" and v.get("codec_name") in ("vp8", "vp9") and
             all(s.get("codec_name") in ("opus", "vorbis") for s in audio))):
        raise ValueError("Use H.264/AAC MP4 or VP8/VP9 WebM for browser playback; convert this file first")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Install FFmpeg before registering videos")
    check = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                            "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"],
                           capture_output=True, timeout=60)
    if check.returncode:
        raise ValueError("The first video frame could not be decoded")
    return {"duration_seconds": round(duration, 3), "width": v["width"], "height": v["height"],
            "video_codec": v["codec_name"], "has_audio": bool(audio), "validation": "metadata_and_first_frame"}


def extract_frames(path, outdir, count=6):
    if not 1 <= count <= 24:
        raise ValueError("Frame count must be between 1 and 24")
    try:
        import cv2
    except ImportError:
        raise RuntimeError("Install the analysis extras: pip install -e '.[analysis]'") from None
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    try:
        fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or total <= 0:
            raise ValueError("Video could not be decoded or has invalid timing")
        duration = total / fps
        frames = []
        # Midpoints avoid the black first/last frame; time-based, not every Nth frame.
        for i in range(count):
            t = duration * (i + .5) / count
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f"Frame extraction failed near {t:.2f}s")
            height, width = frame.shape[:2]
            if max(height, width) > 768:
                scale = 768 / max(height, width)
                frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
            target = outdir / f"frame_{i:02d}.jpg"
            if not cv2.imwrite(str(target), frame, [cv2.IMWRITE_JPEG_QUALITY, 82]):
                raise ValueError("Failed to write sampled frame")
            frames.append({"path": str(target), "timestamp_seconds": round(t, 3), "sha256": file_hash(target)})
        return duration, frames
    finally:
        cap.release()


def prepare(workspace, whisper_model="base", frames=6, language=None, force=False):
    workspace = Path(workspace).resolve()
    model = None
    results, errors = [], []
    for v in load_catalog(workspace):
        try:
            if not v.get("media_path"):
                raise ValueError("No local media file; restore the original video first")
            media = inside(workspace, v["media_path"])
            media_sha = file_hash(media)
            if v.get("media_sha256") and v["media_sha256"] != media_sha:
                raise ValueError("Media hash differs from the registered stimulus")
            out = workspace / "evidence" / (v["video_id"] + ".json")
            config = {"media_sha256": media_sha, "whisper_model": whisper_model,
                      "frame_count": frames, "requested_language": language}
            if out.exists() and not force:
                previous = read_json(out)
                if all(previous.get(k) == val for k, val in config.items()):
                    if all(inside(workspace, f["path"]).exists() and file_hash(inside(workspace, f["path"])) == f["sha256"] for f in previous["frames"]):
                        results.append(v["video_id"])
                        continue
            meta = probe(media)
            has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
            if has_audio:
                try:
                    import whisper
                except ImportError:
                    raise RuntimeError("Install analysis extras to transcribe audio with Whisper") from None
                if model is None:
                    model = whisper.load_model(whisper_model)
                transcript = model.transcribe(str(media), language=language, fp16=False)
            else:
                transcript = {"text": "", "language": None, "segments": []}
            duration, sampled = extract_frames(media, workspace / "frames" / v["video_id"], frames)
            for f in sampled:
                f["path"] = str(Path(f["path"]).relative_to(workspace))
            evidence = {"video_id": v["video_id"], "title": v["title"], **config,
                        "duration_seconds": duration, "transcript": transcript["text"],
                        "language": transcript.get("language"),
                        "transcription_status": "ok" if has_audio else "no_audio",
                        "segments": [{k: s.get(k) for k in ("start", "end", "text")}
                                     for s in transcript.get("segments", [])], "frames": sampled}
            write_json(out, evidence)
            results.append(v["video_id"])
        except (Exception,) as exc:
            errors.append({"video_id": v["video_id"], "error": str(exc)})
    write_json(workspace / "preparation_report.json", {"prepared": results, "errors": errors})
    return results, errors
