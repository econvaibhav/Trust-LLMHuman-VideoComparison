"""Recover old free-text runs conservatively; preserve rejected records for review."""
import csv
import re
from pathlib import Path, PureWindowsPath
from .common import csv_cell, digest, legacy_id, read_json, write_json


def parse_run(path):
    path = Path(path)
    match = re.search(r"temp(\d+(?:_\d+)?)_run(\d+)", path.stem)
    if not match:
        raise ValueError("Unknown legacy run filename")
    temp, run = float(match[1].replace("_", ".")), int(match[2])
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"(?m)^# Video Path:\s*", text)[1:]
    results = []
    for block in blocks:
        original_path, _, body = block.partition("\n")
        name = PureWindowsPath(original_path.strip()).name
        clean = body.replace("*", "").strip("#\n \r")
        scores = re.findall(r"(?im)^\s*[#\-\s]*trust[_ ]score\s*:\s*([+-]?\d+(?:\.\d+)?)", clean)
        score = float(scores[0]) if len(scores) == 1 else None
        def field(label):
            m = re.search(r"(?ims)^\s*" + label + r"\s*:\s*(.*?)(?=^\s*(?:trust_score|why_test_score|factor_choice|full_summary|short_summary)\s*:|\Z)", clean)
            return m[1].strip().strip("#\n ") if m else ""
        fields = {"rationale": field("why_test_score"), "factors_text": field("factor_choice"),
                  "full_summary": field("full_summary"), "short_summary": field("short_summary")}
        reasons = []
        if score is None or not 0 <= score <= 10:
            reasons.append("missing_ambiguous_or_invalid_score")
        if not all(fields.values()):
            reasons.append("missing_fields")
        if temp == 2:
            reasons.append("temperature_2_requires_manual_review")
        results.append({"video_id": legacy_id(name), "file_name": name, "source_run": path.name,
                        "temperature": temp, "repeat": run, "trust_score": score,
                        **fields, "status": "needs_review" if reasons else "ok",
                        "review_reasons": reasons, "model": "legacy_model_unverified",
                        "evidence_mode": "legacy_enriched", "prompt_version": "legacy_unverified",
                        "is_demo": False, "job_id": digest([path.name, name]), "raw_output": body.strip()})
    return results


def recover(source, destination):
    import tempfile
    import zipfile
    source = Path(source)
    if source.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(source) as archive:
            root = Path(td)
            for member in archive.infolist():
                target = (root / member.filename).resolve()
                if not target.is_relative_to(root.resolve()) or member.file_size > 32 * 1024 * 1024:
                    raise ValueError("Unsafe archive member")
                if member.is_dir() or Path(member.filename).name.lower() == "credentials.txt":
                    continue
                if Path(member.filename).suffix.lower() not in (".json", ".txt"):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
            return _recover(root, destination)
    return _recover(source, destination)


def _recover(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Recovery requires an empty workspace; existing studies are never overwritten")
    destination.mkdir(parents=True, exist_ok=True)
    corpus_path = source / "english_data_with_classifications.json"
    corpus = read_json(corpus_path if corpus_path.exists() else source / "combined_english_data.json")
    normalized = [{"video_id": legacy_id(v["file_name"]), "title": Path(v["file_name"]).stem,
                   "file_name": v["file_name"], "transcript": v["transcription"],
                   "legacy_summary": v.get("summary"), "metadata": v.get("metadata", {}),
                   "comments": v.get("comments", []), "classification": v.get("classification"),
                   "topic_models": v.get("topic_models"), "media_path": None, "media_sha256": None}
                  for v in corpus]
    ids = {v["video_id"] for v in normalized}
    if len(ids) != len(normalized):
        raise ValueError("Duplicate normalized legacy filenames; resolve before importing")
    all_rows = []
    for path in sorted((source / "Main_Trust_Analysis_LLM").glob("*.txt")):
        rows = parse_run(path)
        for row in rows:
            if row["video_id"] not in ids:
                row["status"] = "needs_review"
                row["review_reasons"].append("video_not_in_catalog")
        all_rows.extend(rows)
    write_json(destination / "catalog.json", normalized)
    # Imported analyses remain separate from a new, prospective experiment.
    with (destination / "legacy_analyses.jsonl").open("w", encoding="utf-8") as f:
        import json
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    fields = [k for k in all_rows[0] if k != "raw_output"] if all_rows else []
    with (destination / "legacy_ratings.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k: csv_cell(row[k]) for k in fields} for row in all_rows)
    report = {"videos": len(corpus), "run_files": len({r["source_run"] for r in all_rows}),
              "logged_evaluations": len(all_rows), "accepted_structure": sum(r["status"] == "ok" for r in all_rows),
              "requires_review": sum(r["status"] != "ok" for r in all_rows),
              "metadata_present": sum(bool(v.get("metadata")) for v in corpus),
              "comments_present": sum(bool(v.get("comments")) for v in corpus),
              "summary_present": sum(v.get("summary") not in (None, "", "No summary available") for v in corpus),
              "note": "Parsed structure is not evidence that scores or explanations are correct. Model identity and prompt were not logged per run."}
    write_json(destination / "recovery_statistics.json", report)
    from .__main__ import study_config
    write_json(destination / "study.json", study_config(len(normalized)))
    conversations = source / "conversation_history.txt"
    if conversations.exists():
        # No reliable video IDs were recorded; preserve these separately.
        (destination / "unlinked_interviews.txt").write_text(conversations.read_text(encoding="utf-8"), encoding="utf-8")
        report["interview_linkage"] = "Historical conversation sections lack reliable video/session linkage; not included in comparisons."
        write_json(destination / "recovery_statistics.json", report)
    return report
