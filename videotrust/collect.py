"""YouTube Data API collection, stable IDs, optional downloads and VADER."""
import os
import re
from pathlib import Path
from urllib.parse import urlencode
from .common import file_hash, json_request, now, write_json


def collect(workspace, query, regions, limit=20, download=False, sentiment=False, request=json_request):
    if not 1 <= limit <= 500 or not regions or not all(re.fullmatch("[A-Z]{2}", r) for r in regions):
        raise ValueError("Use 1–500 videos and two-letter uppercase region codes")
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise ValueError("Set YOUTUBE_API_KEY")
    workspace = Path(workspace).resolve()
    if (workspace / "catalog.json").exists():
        raise ValueError("Use a new workspace; collection never overwrites a catalog")
    workspace.mkdir(parents=True, exist_ok=True)
    analyzer = None
    if sentiment:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
    def api(resource, **params):
        return request("https://www.googleapis.com/youtube/v3/" + resource + "?" + urlencode({"key": key, **params}))
    seen, rows, issues = set(), [], []
    states = {r: {"page": None, "done": False} for r in dict.fromkeys(regions)}
    # Round-robin region queries. Availability region is not nationality/origin.
    while len(rows) < limit and any(not s["done"] for s in states.values()):
        for region, state in states.items():
            if state["done"] or len(rows) >= limit:
                continue
            params = dict(part="snippet", q=query, type="video", videoDuration="short", regionCode=region,
                          maxResults=min(5, limit - len(rows)), order="relevance", videoEmbeddable="true")
            if state["page"]:
                params["pageToken"] = state["page"]
            try:
                page = api("search", **params)
            except RuntimeError as exc:
                issues.append({"region": region, "stage": "search", "error": str(exc)})
                state["done"] = True
                continue
            state["page"] = page.get("nextPageToken")
            state["done"] = not bool(state["page"])
            for item in page.get("items", []):
                vid = item["id"]["videoId"]
                if vid in seen:
                    continue
                seen.add(vid)
                try:
                    metadata = api("videos", part="snippet,contentDetails,statistics,topicDetails,liveStreamingDetails", id=vid).get("items", [])
                    if not metadata or metadata[0].get("liveStreamingDetails"):
                        continue
                    meta = metadata[0]
                    comments = []
                    try:
                        comment_data = api("commentThreads", part="snippet", videoId=vid, maxResults=10,
                                           order="relevance", textFormat="plainText")
                        for c in comment_data.get("items", []):
                            s = c["snippet"]["topLevelComment"]["snippet"]
                            row = {"comment": s["textDisplay"], "likes": s.get("likeCount", 0)}
                            if analyzer:
                                row["comment_sentiment"] = analyzer.polarity_scores(row["comment"])
                            comments.append(row)
                    except RuntimeError as exc:
                        issues.append({"video_id": vid, "stage": "comments", "error": str(exc)})
                    row = {"video_id": vid, "title": meta["snippet"]["title"],
                           "source_url": "https://www.youtube.com/watch?v=" + vid,
                           "query": query, "search_region": region, "collected_at": now(),
                           "metadata": {k: meta.get(k, {}) for k in ("snippet", "contentDetails", "statistics", "topicDetails")},
                           "comments": comments, "media_path": None, "media_sha256": None}
                    if download:
                        try:
                            from yt_dlp import YoutubeDL
                            media_dir = workspace / "media"
                            media_dir.mkdir(exist_ok=True)
                            with YoutubeDL({"format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]",
                                            "outtmpl": str(media_dir / "%(id)s.%(ext)s"), "noplaylist": True,
                                            "merge_output_format": "mp4", "retries": 3, "quiet": True,
                                            "socket_timeout": 30}) as ydl:
                                ydl.download([row["source_url"]])
                            path = media_dir / (vid + ".mp4")
                            if not path.is_file():
                                raise ValueError("No MP4 produced")
                            row["media_path"] = str(path.relative_to(workspace))
                            row["media_sha256"] = file_hash(path)
                        except Exception:
                            issues.append({"video_id": vid, "stage": "download", "error": "Download failed; restore authorized local media before serving"})
                    rows.append(row)
                    write_json(workspace / "catalog.json", rows)
                except RuntimeError as exc:
                    issues.append({"video_id": vid, "stage": "metadata", "error": str(exc)})
    write_json(workspace / "collection_report.json", {"requested": limit, "collected": len(rows), "issues": issues})
    return rows, issues
