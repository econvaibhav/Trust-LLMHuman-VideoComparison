"""SQLite-backed consent, random assignment, resumable sessions and ratings."""
import hashlib
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from .common import digest, finite_number, now


class StudyError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, workspace, catalog, config):
        self.path = Path(workspace) / "responses.sqlite3"
        self.catalog = {r["video_id"]: r for r in catalog}
        self.config = config
        self.catalog_hash = digest(catalog)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS study_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
              session_id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
              created_at TEXT NOT NULL, consent_version TEXT NOT NULL,
              order_json TEXT NOT NULL, catalog_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS exposures(
              session_id TEXT NOT NULL REFERENCES sessions(session_id), video_id TEXT NOT NULL,
              assigned_at TEXT NOT NULL, PRIMARY KEY(session_id, video_id));
            CREATE TABLE IF NOT EXISTS ratings(
              session_id TEXT NOT NULL REFERENCES sessions(session_id), video_id TEXT NOT NULL,
              trust_score INTEGER NOT NULL CHECK(trust_score BETWEEN 0 AND 10),
              confidence INTEGER CHECK(confidence BETWEEN 0 AND 10), rationale TEXT NOT NULL,
              watch_seconds REAL NOT NULL, elapsed_seconds REAL NOT NULL,
              recorded_at TEXT NOT NULL, payload_hash TEXT NOT NULL,
              PRIMARY KEY(session_id, video_id));
            CREATE TABLE IF NOT EXISTS interview_turns(
              session_id TEXT NOT NULL REFERENCES sessions(session_id), video_id TEXT NOT NULL,
              turn INTEGER NOT NULL, request_id TEXT NOT NULL, answer TEXT NOT NULL,
              next_question TEXT, model_json TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(session_id,video_id,turn), UNIQUE(session_id,request_id));
            CREATE TABLE IF NOT EXISTS interview_results(
              session_id TEXT NOT NULL REFERENCES sessions(session_id), video_id TEXT NOT NULL,
              result_json TEXT NOT NULL, PRIMARY KEY(session_id,video_id));
            """)
            signature = digest({"catalog": catalog, "config": config})
            previous = db.execute("SELECT value FROM study_meta WHERE key='signature'").fetchone()
            if previous and previous[0] != signature:
                raise ValueError("Study catalog/config changed. Start a new workspace to avoid mixing studies.")
            db.execute("INSERT OR IGNORE INTO study_meta VALUES('signature',?)", (signature,))
            db.execute("INSERT OR IGNORE INTO study_meta VALUES('catalog_json',?)", (json.dumps(catalog, ensure_ascii=False),))
            db.execute("INSERT OR IGNORE INTO study_meta VALUES('study_json',?)", (json.dumps(config, ensure_ascii=False),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def session(self, db, token):
        hashed = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute("SELECT * FROM sessions WHERE token_hash=?", (hashed,)).fetchone()
        if not row:
            raise StudyError("Session not found. Start a new session.", 401)
        return row

    def create(self, consent):
        if consent is not True:
            raise StudyError("Please consent before starting.")
        order = list(self.catalog)
        secrets.SystemRandom().shuffle(order)
        order = order[:self.config.get("videos_per_session", len(order))]
        token = secrets.token_urlsafe(32)
        sid = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)", (
                sid, hashlib.sha256(token.encode()).hexdigest(), now(),
                self.config["consent_version"], json.dumps(order), self.catalog_hash))
        return {"token": token, **self.current(token)}

    def _current(self, db, session):
        order = json.loads(session["order_json"])
        mode = self.config.get("response_mode", "direct")
        table = "interview_results" if mode in ("interview", "paired") else "ratings"
        rated = {r[0] for r in db.execute(f"SELECT video_id FROM {table} WHERE session_id=?",
                                         (session["session_id"],))}
        next_id = next((v for v in order if v not in rated), None)
        result = {"session_id": session["session_id"], "completed": len(rated),
                  "total": len(order), "done": next_id is None, "video": None}
        if next_id:
            db.execute("INSERT OR IGNORE INTO exposures VALUES(?,?,?)",
                       (session["session_id"], next_id, now()))
            v = self.catalog[next_id]
            # Do not leak model scores, generated summaries, transcripts or comments.
            result["video"] = {"video_id": next_id, "title": v["title"],
                               "media_url": "/media/" + next_id}
            rating_saved = bool(db.execute("SELECT 1 FROM ratings WHERE session_id=? AND video_id=?", (session["session_id"], next_id)).fetchone())
            result["stage"] = "interview" if mode == "interview" or (mode == "paired" and rating_saved) else "rating"
            if result["stage"] == "interview":
                result["interview"] = self.interview_state(db, session["session_id"], next_id)
        return result

    def current(self, token):
        with self.connect() as db:
            return self._current(db, self.session(db, token))

    def rate(self, token, payload):
        if self.config.get("response_mode") == "interview":
            raise StudyError("This study collects interviews, not direct ratings", 409)
        vid, score = payload.get("video_id"), payload.get("trust_score")
        confidence = payload.get("confidence")
        rationale = payload.get("rationale", "")
        watched = payload.get("watch_seconds", 0)
        if not isinstance(vid, str) or type(score) is not int or not 0 <= score <= 10:
            raise StudyError("Choose a trust score from 0 to 10.")
        if confidence is not None and (type(confidence) is not int or not 0 <= confidence <= 10):
            raise StudyError("Confidence must be an integer from 0 to 10.")
        if not isinstance(rationale, str) or len(rationale) > 2000:
            raise StudyError("The explanation must be at most 2,000 characters.")
        if not finite_number(watched, 0, 86400):
            raise StudyError("Invalid playback duration.")
        canonical = {"video_id": vid, "trust_score": score, "confidence": confidence,
                     "rationale": rationale.strip(), "watch_seconds": watched}
        ph = digest(canonical)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            session = self.session(db, token)
            prior = db.execute("SELECT payload_hash FROM ratings WHERE session_id=? AND video_id=?",
                               (session["session_id"], vid)).fetchone()
            if prior:
                if prior[0] != ph:
                    raise StudyError("This video already has a saved response.", 409)
                return self._current(db, session)  # Safe retry after interrupted connection.
            current = self._current(db, session)
            if current["done"] or current["video"]["video_id"] != vid:
                raise StudyError("This video is not your current assigned video.", 409)
            assigned = db.execute("SELECT assigned_at FROM exposures WHERE session_id=? AND video_id=?",
                                  (session["session_id"], vid)).fetchone()[0]
            stamp = now()
            elapsed = max(0, (datetime.fromisoformat(stamp) - datetime.fromisoformat(assigned)).total_seconds())
            db.execute("INSERT INTO ratings VALUES(?,?,?,?,?,?,?,?,?)", (
                session["session_id"], vid, score, confidence, rationale.strip(), watched,
                round(elapsed, 3), stamp, ph))
            return self._current(db, session)

    def ratings(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT r.session_id,r.video_id,r.trust_score,
              r.confidence,r.rationale,r.watch_seconds,r.elapsed_seconds,r.recorded_at,
              s.consent_version,s.catalog_hash,e.assigned_at
              FROM ratings r JOIN sessions s USING(session_id)
              JOIN exposures e USING(session_id,video_id) ORDER BY r.recorded_at""")]

    def session_counts(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    def interview_state(self, db, sid, vid):
        from .interview import FIRST_QUESTION
        turns = db.execute("SELECT * FROM interview_turns WHERE session_id=? AND video_id=? ORDER BY turn", (sid, vid)).fetchall()
        messages = [{"role": "assistant", "content": FIRST_QUESTION}]
        for row in turns:
            messages.append({"role": "user", "content": row["answer"]})
            if row["next_question"]:
                messages.append({"role": "assistant", "content": row["next_question"]})
        pending = bool(turns and len(turns) < self.config.get("interview_turns", 3) and turns[-1]["next_question"] is None)
        return {"messages": messages, "answered": len(turns), "pending_question": pending,
                "retry_payload": {"video_id": vid, "request_id": turns[-1]["request_id"], "answer": turns[-1]["answer"], "expected_turn": turns[-1]["turn"]} if pending else None,
                "max_turns": self.config.get("interview_turns", 3),
                "ready_to_finish": len(turns) >= self.config.get("interview_turns", 3)}

    def participant_rows(self, measure=None):
        direct = [{**r, "measure": "direct_rating"} for r in self.ratings()]
        if self.config.get("response_mode") == "direct" or self.config.get("response_mode") is None:
            return direct
        with self.connect() as db:
            inferred = [{"session_id": r["session_id"], "video_id": r["video_id"],
                     **json.loads(r["result_json"]), "consent_version": r["consent_version"],
                     "catalog_hash": r["catalog_hash"]} for r in db.execute(
                "SELECT i.*,s.consent_version,s.catalog_hash FROM interview_results i JOIN sessions s USING(session_id)")]
        if self.config.get("response_mode") == "interview" or measure == "interview_inferred":
            return inferred
        return direct if measure == "direct_rating" else direct + inferred

    def progress_summary(self):
        with self.connect() as db:
            sessions = db.execute("SELECT * FROM sessions").fetchall()
            table = "interview_results" if self.config.get("response_mode") in ("paired", "interview") else "ratings"
            complete = 0
            for s in sessions:
                done = {r[0] for r in db.execute(f"SELECT video_id FROM {table} WHERE session_id=?", (s["session_id"],))}
                complete += set(json.loads(s["order_json"])).issubset(done)
            return {"sessions": len(sessions), "completed_sessions": complete, "active_sessions": len(sessions) - complete}

    def interview_export(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM interview_turns ORDER BY session_id,video_id,turn")]
