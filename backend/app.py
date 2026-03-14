from flask import Flask, request, jsonify, g, Response
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "practice.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

app = Flask(__name__)
CORS(app)


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript(
        """
    CREATE TABLE IF NOT EXISTS songs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      composer TEXT,
      source_file TEXT,
      total_measures INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS measure_groups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id INTEGER NOT NULL,
      start_measure INTEGER NOT NULL,
      end_measure INTEGER NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      group_size INTEGER GENERATED ALWAYS AS (end_measure - start_measure + 1) VIRTUAL
    );

    CREATE TABLE IF NOT EXISTS practice_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id INTEGER NOT NULL,
      measure_group_id INTEGER NOT NULL,
      practiced_at TEXT DEFAULT (datetime('now')),
      rating TEXT CHECK (rating IN ('easy','medium','hard','snooze')) NOT NULL,
      duration_seconds INTEGER,
      notes TEXT,
      FOREIGN KEY (song_id) REFERENCES songs(id),
      FOREIGN KEY (measure_group_id) REFERENCES measure_groups(id)
    );
    """
    )

    # Safe migration: add SM-2 columns if they don't exist yet
    for col, definition in [
        ("interval_days", "REAL DEFAULT 0"),
        ("ease_factor", "REAL DEFAULT 2.5"),
        ("next_due", "TEXT DEFAULT NULL"),
        ("last_rating", "TEXT DEFAULT NULL"),
    ]:
        try:
            db.execute(f"ALTER TABLE measure_groups ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    db.commit()


# Initialize with app context
os.makedirs(DATA_DIR, exist_ok=True)
with app.app_context():
    init_db()


@app.before_request
def before_request():
    get_db()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


# helpers
def row_to_dict(r: sqlite3.Row):
    return {k: r[k] for k in r.keys()}


def file_candidates_from_song_and_measure(song_row: sqlite3.Row, measure: int) -> List[str]:
    src = song_row.get("source_file") or ""
    folder = os.path.dirname(src)
    base = os.path.splitext(os.path.basename(src))[0] or ""
    prefix = (folder + "/") if folder and folder != "." else ""
    return [f"{prefix}{base}_measure_{measure}.musicxml", f"{prefix}{base}_measure_{measure}.mxl"]


# SM-2 constants
_FIRST_INTERVAL = {"easy": 1.0, "medium": 0.5, "hard": 0.1}  # days
_EASE_DELTA = {"easy": 0.15, "medium": 0.0, "hard": -0.15, "snooze": 0.0}
_MIN_EASE = 1.3
_SNOOZE_MINUTES = 30


def compute_sm2(interval_days: float, ease_factor: float, rating: str):
    """Compute new SM-2 state. Returns (new_interval_days, new_ease_factor, next_due_iso)."""
    now = datetime.utcnow()

    if rating == "snooze":
        next_due = now + timedelta(minutes=_SNOOZE_MINUTES)
        return interval_days, ease_factor, next_due.isoformat()

    new_ease = max(ease_factor + _EASE_DELTA[rating], _MIN_EASE)

    if interval_days == 0:
        new_interval = _FIRST_INTERVAL[rating]
    elif rating == "easy":
        new_interval = max(interval_days * ease_factor * 1.3, 1.0)
    elif rating == "medium":
        new_interval = max(interval_days * ease_factor, 1.0)
    else:  # hard
        new_interval = max(interval_days * 0.5, 0.1)

    next_due = now + timedelta(days=new_interval)
    return new_interval, new_ease, next_due.isoformat()


# CRUD endpoints


@app.route("/api/practice", methods=["POST"])
def log_practice():
    data = request.get_json() or {}

    rating = data.get("rating")
    if rating not in ("easy", "medium", "hard", "snooze"):
        return jsonify({"error": "rating required and must be one of easy/medium/hard/snooze"}), 400

    song_id = data.get("song_id")
    measure_group_id = data.get("measure_group_id")
    if not song_id or not measure_group_id:
        return jsonify({"error": "song_id and measure_group_id required"}), 400

    duration_seconds = data.get("duration_seconds")
    notes = data.get("notes")

    db = get_db()

    cur = db.execute(
        "INSERT INTO practice_sessions (song_id, measure_group_id, rating, duration_seconds, notes) VALUES (?, ?, ?, ?, ?)",
        (song_id, measure_group_id, rating, duration_seconds, notes),
    )

    # Update SM-2 state on the measure group
    mg = db.execute(
        "SELECT interval_days, ease_factor FROM measure_groups WHERE id = ?",
        (measure_group_id,),
    ).fetchone()

    if mg:
        new_interval, new_ease, next_due = compute_sm2(
            mg["interval_days"] or 0,
            mg["ease_factor"] or 2.5,
            rating,
        )
        db.execute(
            "UPDATE measure_groups SET interval_days=?, ease_factor=?, next_due=?, last_rating=? WHERE id=?",
            (new_interval, new_ease, next_due, rating, measure_group_id),
        )

    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/songs", methods=["GET"])
def list_songs():
    db = get_db()
    rows = db.execute("SELECT * FROM songs ORDER BY title").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/measure-groups", methods=["GET"])
def list_measure_groups():
    db = get_db()
    rows = db.execute(
        "SELECT mg.*, s.title AS song_title FROM measure_groups mg JOIN songs s ON s.id = mg.song_id ORDER BY mg.created_at DESC"
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/practice-sessions", methods=["GET"])
def list_practice_sessions():
    db = get_db()
    rows = db.execute("""
        SELECT
            ps.*,
            s.title as song_title,
            mg.start_measure,
            mg.end_measure
        FROM practice_sessions ps
        JOIN songs s ON s.id = ps.song_id
        JOIN measure_groups mg ON mg.id = ps.measure_group_id
        ORDER BY ps.practiced_at DESC
    """).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/practice-sessions", methods=["DELETE"])
def clear_practice_sessions():
    db = get_db()
    db.execute("DELETE FROM practice_sessions")
    # Also reset SM-2 state so the algorithm starts fresh
    db.execute("UPDATE measure_groups SET interval_days=0, ease_factor=2.5, next_due=NULL, last_rating=NULL")
    db.commit()
    return jsonify({"status": "ok"})


class ProficiencyLevel(Enum):
    PROFICIENT = 4
    DECENT = 3
    NEEDS_PRACTICE = 2
    UNLEARNED = 1


@dataclass
class MeasureItem:
    id: str
    start: int
    end: int
    interval_days: float
    ease_factor: float
    next_due: Optional[str]
    last_rating: Optional[str]
    practice_count: int
    last_practiced: Optional[str]
    category: str

    @property
    def is_group(self) -> bool:
        return self.start != self.end

    @property
    def is_new(self) -> bool:
        return self.practice_count == 0

    @property
    def is_overdue(self) -> bool:
        if self.practice_count == 0:
            return False
        if self.next_due is None:
            return True  # Old data with no next_due — treat as due immediately
        return self.next_due <= datetime.utcnow().isoformat()

    @property
    def overdue_seconds(self) -> float:
        """Seconds past due (larger = more overdue). Returns inf for old data with no next_due."""
        if self.next_due is None:
            return float("inf")
        return (datetime.utcnow() - datetime.fromisoformat(self.next_due)).total_seconds()

    @staticmethod
    def category_from_interval(interval_days: float, practice_count: int) -> str:
        if practice_count == 0:
            return "unlearned"
        if interval_days < 1:
            return "needs_practice"
        if interval_days < 7:
            return "decent"
        return "proficient"

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "MeasureItem":
        interval = row["interval_days"] or 0
        practice_count = row["practice_count"] or 0
        return cls(
            id=row["id"],
            start=row["start_measure"],
            end=row["end_measure"],
            interval_days=interval,
            ease_factor=row["ease_factor"] or 2.5,
            next_due=row["next_due"],
            last_rating=row["last_rating"],
            practice_count=practice_count,
            last_practiced=row["last_practiced"],
            category=cls.category_from_interval(interval, practice_count),
        )


def get_next_measure(song_id: int):
    """Get next measure to practice using spaced repetition algorithm."""
    db = get_db()

    song = db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not song:
        return jsonify({"error": "Song not found"}), 404

    measures = get_all_measures(db, song_id)
    if not measures["single"] and not measures["groups"]:
        return jsonify({"measure": 1})

    eligible_items = get_eligible_items(measures)
    if not eligible_items:
        return jsonify({"measure": 1})

    next_item = select_next_item(eligible_items)
    return create_response(next_item)


@app.route("/api/songs/<int:song_id>/next-measure", methods=["GET"])
def next_measure_for_song(song_id: int):
    return get_next_measure(song_id)


def get_all_measures(db, song_id: int) -> Dict[str, List[MeasureItem]]:
    rows = db.execute("""
        SELECT
            mg.id, mg.start_measure, mg.end_measure,
            mg.interval_days, mg.ease_factor, mg.next_due, mg.last_rating,
            COUNT(ps.id) as practice_count,
            MAX(ps.practiced_at) as last_practiced
        FROM measure_groups mg
        LEFT JOIN practice_sessions ps ON mg.id = ps.measure_group_id
        WHERE mg.song_id = ?
        GROUP BY mg.id, mg.start_measure, mg.end_measure
        ORDER BY mg.start_measure, mg.end_measure
    """, (song_id,)).fetchall()

    single_measures = []
    measure_groups = []

    for row in rows:
        item = MeasureItem.from_db_row(row)
        if item.is_group:
            measure_groups.append(item)
        else:
            single_measures.append(item)

    return {"single": single_measures, "groups": measure_groups}


def get_eligible_items(measures: Dict[str, List[MeasureItem]]) -> List[MeasureItem]:
    """Determine which items are eligible for practice.

    Learning window: expands one measure at a time. The next single measure is
    unlocked once all previous singles have interval_days >= 1 (at least 'decent').
    Multi-measure groups unlock when all their component singles are decent.
    """
    single_measures = measures["single"]
    measure_groups = measures["groups"]

    # Advance window as far as singles are decent (interval >= 1 day)
    window_size = 1
    while window_size <= len(single_measures):
        if all(m.interval_days >= 1 for m in single_measures[:window_size]):
            window_size += 1
        else:
            break

    window_singles = single_measures[:window_size]

    # Groups unlock when every measure in their range is decent
    single_intervals = {m.start: m.interval_days for m in single_measures}
    window_groups = [
        g for g in measure_groups
        if all(single_intervals.get(n, 0) >= 1 for n in range(g.start, g.end + 1))
    ]

    return window_singles + window_groups


def select_next_item(eligible_items: List[MeasureItem]) -> MeasureItem:
    """Select next item with due-date priority and small random-review chances."""
    overdue = [m for m in eligible_items if m.is_overdue]
    new_items = [m for m in eligible_items if m.is_new]
    upcoming = [m for m in eligible_items if not m.is_overdue and not m.is_new]

    # Small chance to surprise-review already-learned items (even if not due)
    proficient = [m for m in eligible_items if m.category == "proficient"]
    decent = [m for m in eligible_items if m.category == "decent"]

    roll = random.random()
    if roll < 0.05 and proficient:
        return random.choice(proficient)
    if roll < 0.15 and decent:
        return random.choice(decent)

    # Priority 1: most overdue item
    if overdue:
        return max(overdue, key=lambda m: m.overdue_seconds)

    # Priority 2: introduce the next new (unlearned) measure
    if new_items:
        return min(new_items, key=lambda m: m.start)

    # Priority 3: whatever is due soonest
    if upcoming:
        return min(upcoming, key=lambda m: m.next_due or "")

    return eligible_items[0]


def create_response(item: MeasureItem) -> Response:
    return jsonify({
        "id": item.id,
        "stats": {
            "category": item.category,
            "interval_days": item.interval_days,
            "ease_factor": item.ease_factor,
            "next_due": item.next_due,
            "last_rating": item.last_rating,
            "practice_count": item.practice_count,
            "last_practiced": item.last_practiced,
            "is_group": item.is_group,
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
