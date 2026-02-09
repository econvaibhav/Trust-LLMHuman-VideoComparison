import argparse
import os
import secrets
import shutil
import sys
from pathlib import Path
from .common import file_hash, load_catalog, read_json, write_json

ROOT = Path(__file__).resolve().parent.parent


def study_config(count, is_demo=False):
    return {"title": "Video trust study", "is_demo": is_demo, "consent_version": "demo-v2" if is_demo else "draft-v1",
            "videos_per_session": min(count, 3), "contact": "Set the researcher contact in study.json.",
            "consent_text": ("This local demonstration uses part_46, a Finnish news video. Your rating, optional explanation and playback time are saved on this computer. No name or email is requested. No API calls are made. The researcher view includes a recorded example model score. You may stop at any time." if is_demo else
                             "DRAFT — replace this text with your study information, researcher contact, retention period, withdrawal procedure and consent wording before recruitment.")}


def init_demo(workspace, interview=False, paired=False):
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Choose an empty workspace; existing responses are never overwritten")
    shutil.copytree(Path(__file__).parent / "demo", workspace, dirs_exist_ok=True)
    if interview or paired:
        cfg = read_json(workspace / "study.json")
        cfg.update(response_mode="paired" if paired else "interview", interview_turns=3, consent_version="demo-interview-v2")
        cfg["consent_text"] = "This local demonstration uses part_46, a Finnish news video, and fixed interview questions. Your responses are saved on this computer. No API calls are made and no score is inferred from your answers. The researcher view includes a recorded example model score. You may stop at any time."
        write_json(workspace / "study.json", cfg)


def register(workspace, media_dir, skip_invalid=False, response_mode="direct"):
    if (workspace / "catalog.json").exists():
        raise ValueError("Choose a new workspace")
    from .media import inspect_media
    paths = [media_dir] if media_dir.is_file() else sorted(p for p in media_dir.rglob("*") if p.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv") and p.is_file())
    checked, invalid = [], []
    for source in paths:
        try:
            checked.append((source, inspect_media(source)))
        except (ValueError, OSError) as exc:
            invalid.append({"file": source.name, "error": str(exc)})
    write_json(workspace / "registration_report.json", {"valid": [p.name for p, _ in checked], "invalid": invalid})
    if invalid and not skip_invalid:
        raise ValueError(f"{len(invalid)} video(s) failed validation; see registration_report.json. Repair them or use --skip-invalid.")
    rows, seen = [], set()
    for source, media_info in checked:
        sha = file_hash(source)
        if sha in seen:
            continue
        seen.add(sha)
        vid = "local_" + sha[:24]
        target = workspace / "media" / (vid + source.suffix.lower())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append({"video_id": vid, "title": source.stem, "media_path": str(target.relative_to(workspace)),
                     "media_sha256": sha, "media_info": media_info, "original_filename": source.name, "metadata": {}, "comments": []})
    if not rows:
        raise ValueError("No video files were found")
    write_json(workspace / "catalog.json", rows)
    write_json(workspace / "study.json", {**study_config(len(rows)), "response_mode": response_mode})
    return len(rows)


def init_example(workspace, response_mode="paired"):
    """Create a separate live pilot from the bundled clip, without example scores."""
    clip = Path(__file__).parent / "demo" / "media" / "part_46.mp4"
    register(workspace, clip, response_mode=response_mode)
    cfg = read_json(workspace / "study.json")
    cfg.update(title="Video trust study", contact="vaibhav.agarwal@tum.de",
               consent_version="local-pilot-v1", interview_turns=3,
               consent_text="This is a local pilot using part_46. Your responses are saved on this computer. Live interviews send your written answers to OpenAI to ask follow-up questions and interpret your responses. Video analysis sends a transcript and sampled images to OpenAI. Do not enter names or other personal information. You may stop at any time. Replace this pilot information with your institution's approved study information before inviting participants.")
    write_json(workspace / "study.json", cfg)


def restore_media(workspace, media_dir):
    if (workspace / "responses.sqlite3").exists():
        raise ValueError("Restore media before starting a study, or use a new workspace")
    catalog = load_catalog(workspace)
    candidates = {}
    for p in media_dir.rglob("*"):
        if p.is_file():
            candidates.setdefault(p.name, []).append(p)
    missing = []
    for row in catalog:
        options = candidates.get(row.get("file_name", row["video_id"] + ".mp4"), [])
        if len(options) != 1:
            missing.append(row["video_id"])
            continue
        source = options[0]
        target = workspace / "media" / (row["video_id"] + source.suffix.lower())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        row["media_path"] = str(target.relative_to(workspace))
        row["media_sha256"] = file_hash(target)
    write_json(workspace / "catalog.json", catalog)
    write_json(workspace / "media_restore_report.json", {"missing_or_ambiguous": missing})
    if not (workspace / "study.json").exists():
        write_json(workspace / "study.json", study_config(len(catalog)))
    return missing


def main(argv=None):
    p = argparse.ArgumentParser(description="Collect videos, survey people, and compare independent model judgments.")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("demo", "example", "serve", "register", "collect", "prepare", "enrich", "analyze", "recover-legacy", "restore-media", "report", "doctor"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--workspace", type=Path, default=Path("data/demo-part46" if name == "demo" else "data/study"))
        if name in ("demo", "serve"):
            cmd.add_argument("--host", default="127.0.0.1")
            cmd.add_argument("--port", type=int, default=8000)
        if name == "demo":
            mode = cmd.add_mutually_exclusive_group()
            mode.add_argument("--interview", action="store_true")
            mode.add_argument("--paired", action="store_true")
        if name == "register":
            cmd.add_argument("--skip-invalid", action="store_true")
        if name in ("register", "example"):
            cmd.add_argument("--response-mode", choices=["direct", "interview", "paired"], default="paired" if name == "example" else "direct")
        if name == "enrich":
            cmd.add_argument("--model", default="gpt-4o-mini")
            cmd.add_argument("--embedding-model", default="text-embedding-3-small")
            cmd.add_argument("--clusters", type=int, default=10)
            cmd.add_argument("--force", action="store_true")
        if name in ("register", "recover-legacy", "restore-media"):
            cmd.add_argument("--input", required=True, type=Path)
        if name == "collect":
            cmd.add_argument("--query", default="#Shorts politics")
            cmd.add_argument("--regions", nargs="+", default=["DE", "AT", "FI", "FR", "IT", "NL", "PL", "ES", "SE"])
            cmd.add_argument("--limit", type=int, default=20)
            cmd.add_argument("--download", action="store_true")
            cmd.add_argument("--sentiment", action="store_true")
        if name == "prepare":
            cmd.add_argument("--whisper-model", default="base")
            cmd.add_argument("--frames", type=int, default=6)
            cmd.add_argument("--language")
            cmd.add_argument("--force", action="store_true")
        if name == "analyze":
            cmd.add_argument("--model", default="gpt-4o-mini")
            cmd.add_argument("--temperatures", type=float, nargs="+", default=[0])
            cmd.add_argument("--runs", type=int, default=1)
            cmd.add_argument("--evidence-mode", choices=["video_only", "metadata_comments", "legacy_enriched"], default="video_only")
    args = p.parse_args(argv)
    if args.command == "demo" and args.interview and args.workspace == Path("data/demo-part46"):
        args.workspace = Path("data/demo-part46-interview")
    if args.command == "demo" and args.paired and args.workspace == Path("data/demo-part46"):
        args.workspace = Path("data/demo-part46-paired")
    args.workspace = args.workspace.resolve()
    try:
        if args.command in ("demo", "serve"):
            if args.command == "demo" and not (args.workspace / "catalog.json").exists():
                init_demo(args.workspace, args.interview, args.paired)
            if args.command == "demo" and args.interview and read_json(args.workspace / "study.json").get("response_mode") != "interview":
                raise ValueError("Choose a new workspace for the interview demo")
            if args.command == "demo" and args.paired and read_json(args.workspace / "study.json").get("response_mode") != "paired":
                raise ValueError("Choose a new workspace for the paired demo")
            if args.command == "demo" and not read_json(args.workspace / "study.json").get("is_demo"):
                raise ValueError("This workspace is not a demo")
            from .server import create_server
            token = os.environ.get("VIDEOTRUST_ADMIN_TOKEN") or secrets.token_urlsafe(24)
            server = create_server(args.workspace, args.host, args.port, token)
            print(f"Survey: http://{args.host}:{server.server_port}\nResearcher: http://{args.host}:{server.server_port}/researcher\nResearcher token: {token}\nWorkspace: {args.workspace}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        elif args.command == "example":
            init_example(args.workspace, args.response_mode)
            print(f"Created a live part_46 pilot in {args.workspace}. Next: trust-video prepare, trust-video analyze, trust-video serve. Use the same --workspace for each command if you chose a custom folder.")
        elif args.command == "register":
            print(f"Registered {register(args.workspace, args.input, args.skip_invalid, args.response_mode)} valid unique videos. See registration_report.json; edit study.json before recruitment.")
        elif args.command == "restore-media":
            missing = restore_media(args.workspace, args.input)
            print(f"Media restore complete. Missing or ambiguous: {len(missing)}. See media_restore_report.json.")
            return int(bool(missing))
        elif args.command == "recover-legacy":
            from .legacy import recover
            print(recover(args.input, args.workspace))
        elif args.command == "collect":
            from .collect import collect
            rows, issues = collect(args.workspace, args.query, args.regions, args.limit, args.download, args.sentiment)
            if rows:
                write_json(args.workspace / "study.json", study_config(len(rows)))
            print(f"Collected {len(rows)} videos; {len(issues)} issues. See collection_report.json.")
            return int(not rows or len(rows) < args.limit or bool(issues))
        elif args.command == "prepare":
            from .media import prepare
            good, errors = prepare(args.workspace, args.whisper_model, args.frames, args.language, args.force)
            print(f"Prepared {len(good)}; failed {len(errors)}. See preparation_report.json.")
            return int(bool(errors))
        elif args.command == "enrich":
            from .enrich import enrich
            good, errors = enrich(args.workspace, args.model, args.embedding_model, args.clusters, args.force)
            print(f"Enriched {good}; failed {len(errors)}. See enrichment_report.json.")
            return int(bool(errors))
        elif args.command == "doctor":
            from .doctor import doctor
            return doctor(args.workspace)
        elif args.command == "analyze":
            from .llm import analyze
            count, failed = analyze(args.workspace, args.model, args.temperatures, args.runs, args.evidence_mode)
            print(f"New judgments: {count}; failed: {failed}. Completed jobs were skipped.")
            return int(bool(failed))
        elif args.command == "report":
            import csv
            from .common import csv_cell
            from .common import read_jsonl
            from .compare import comparison
            from .storage import Store
            cat = load_catalog(args.workspace)
            cfg = read_json(args.workspace / "study.json")
            rows = Store(args.workspace, cat, cfg).participant_rows()
            analyses = read_jsonl(args.workspace / "analyses.jsonl")
            results = []
            mode = cfg.get("response_mode", "direct")
            measures = ["direct_rating", "interview_inferred"] if mode == "paired" else ["interview_inferred" if mode == "interview" else "direct_rating"]
            for measure in measures:
                data = comparison(cat, rows, analyses, cfg.get("is_demo", False), measure=measure)
                results.extend(comparison(cat, rows, analyses, cfg.get("is_demo", False), group["id"], measure)
                               for group in data["groups"])
                if not data["groups"]:
                    results.append(data)
            write_json(args.workspace / "comparison.json", results)
            columns = ['condition_id', 'participant_measure', 'model', 'resolved_model', 'temperature', 'evidence_mode', 'evidence_set_hash',
                       'prompt_version', 'video_id', 'title', 'human_n', 'human_mean', 'human_sd',
                       'model_n', 'model_mean', 'model_sd', 'gap']
            with (args.workspace / 'comparison.csv').open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                for result in results:
                    group = next((g for g in result['groups'] if g['id'] == result['selected_group']), {})
                    for row in result['rows']:
                        values = {**group, **row, 'condition_id': result['selected_group'], 'participant_measure': result['participant_measure']}
                        writer.writerow({k: csv_cell(values.get(k)) for k in columns})
            print("Saved comparison.json and comparison.csv (each condition is separate).")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
