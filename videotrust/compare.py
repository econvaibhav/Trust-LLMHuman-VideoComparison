"""Descriptive video-level comparisons. Repeated model runs are not participants."""
import math
import statistics as st
from collections import defaultdict
from .common import digest, finite_number


def group_key(row):
    return {k: row.get(k) for k in ("model", "resolved_model", "temperature", "evidence_mode", "prompt_version", "prompt_hash", "evidence_set_hash", "is_demo")}


def interview_agreement(ratings):
    """Match the two participant measures by session AND video, not group means."""
    paired = defaultdict(dict)
    for row in ratings:
        if finite_number(row.get("trust_score"), 0, 10):
            paired[(row["session_id"], row["video_id"])][row["measure"]] = row["trust_score"]
    gaps = [p["interview_inferred"] - p["direct_rating"] for p in paired.values()
            if "direct_rating" in p and "interview_inferred" in p]
    return {"pairs": len(gaps), "mean_absolute_gap": st.mean(map(abs, gaps)) if gaps else None,
            "mean_signed_gap": st.mean(gaps) if gaps else None}


def comparison(catalog, ratings, analyses, is_demo=False, selected=None, measure=None):
    measures = list(dict.fromkeys(r.get("measure", "direct_rating") for r in ratings))
    measure = measure or next(iter(measures), "direct_rating")
    ratings = [r for r in ratings if r.get("measure", "direct_rating") == measure]
    groups = {}
    valid = []
    catalog_by_id = {v["video_id"]: v for v in catalog}
    seen_jobs = set()
    for a in analyses:
        if (a.get("status") != "ok" or a.get("is_demo", False) != is_demo or
                not finite_number(a.get("trust_score"), 0, 10)):
            continue
        video = catalog_by_id.get(a.get("video_id"))
        if video is None or (not is_demo and a.get("media_sha256") != video.get("media_sha256")):
            continue
        if a.get("job_id") and a["job_id"] in seen_jobs:
            continue
        seen_jobs.add(a.get("job_id"))
        gid = digest(group_key(a))[:16]
        groups[gid] = {"id": gid, **group_key(a)}
        valid.append((gid, a))
    selected = selected or next(iter(groups), None)
    if selected and selected not in groups:
        raise ValueError("Unknown model condition")
    hs, ms = defaultdict(list), defaultdict(list)
    for r in ratings:
        if finite_number(r.get("trust_score"), 0, 10):
            hs[r["video_id"]].append(r["trust_score"])
    for gid, a in valid:
        if gid == selected:
            ms[a["video_id"]].append(a)
    rows = []
    for v in catalog:
        human, model = hs[v["video_id"]], ms[v["video_id"]]
        hv = st.mean(human) if human else None
        scores = [a["trust_score"] for a in model]
        mv = st.mean(scores) if scores else None
        rows.append({"video_id": v["video_id"], "title": v["title"],
                     "human_n": len(human), "human_mean": hv,
                     "human_sd": st.stdev(human) if len(human) > 1 else None,
                     "model_n": len(scores), "model_mean": mv,
                     "model_sd": st.stdev(scores) if len(scores) > 1 else None,
                     "gap": hv - mv if hv is not None and mv is not None else None,
                     "model_runs": model})
    paired = [r for r in rows if r["gap"] is not None]
    corr = None
    if len(paired) >= 3:
        x, y = [r["human_mean"] for r in paired], [r["model_mean"] for r in paired]
        if st.pstdev(x) > 0 and st.pstdev(y) > 0:
            corr = st.correlation(x, y)
    rows.sort(key=lambda r: (r["gap"] is None, -abs(r["gap"] or 0), r["title"]))
    return {"groups": list(groups.values()), "selected_group": selected, "rows": rows,
            "participant_measure": measure, "available_measures": measures,
            "summary": {"videos": len(catalog), "responses": len(ratings),
                        "paired_videos": len(paired),
                        "unscored_responses": sum(not finite_number(r.get("trust_score"), 0, 10) for r in ratings),
                        "mean_absolute_gap": st.mean(abs(r["gap"]) for r in paired) if paired else None,
                        "mean_signed_gap": st.mean(r["gap"] for r in paired) if paired else None,
                        "pearson_r": corr}, "is_demo": is_demo}
