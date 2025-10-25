from flask import Flask, request, jsonify, g, Response  # Added Response
from flask_cors import CORS
import sqlite3
import os
from typing import List
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional
import random

DB_PATH = os.path.join(os.path.dirname(__file__), "practice.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")  # optional, not required for schema

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
    db.commit()


# Initialize with app context
os.makedirs(DATA_DIR, exist_ok=True)
with app.app_context():
    init_db()


@app.before_request
def before_request():
    # Ensure DB connection exists for this request
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
    """Construct likely filename(s) for a given song and measure.
    Heuristic: take song.source_file -> dirname/base; produce `${dir}/${base}_measure_${n}.musicxml`
    and also include `.mxl` fallback.
    """
    src = song_row.get("source_file") or ""
    folder = os.path.dirname(src)
    base = os.path.splitext(os.path.basename(src))[0] or ""
    prefix = (folder + "/") if folder and folder != "." else ""
    return [f"{prefix}{base}_measure_{measure}.musicxml", f"{prefix}{base}_measure_{measure}.mxl"]


# CRUD endpoints (minimal)


@app.route("/api/practice", methods=["POST"])
def log_practice():
    data = request.get_json() or {}
    
    # Validate required fields
    rating = data.get("rating")
    if rating not in ("easy", "medium", "hard", "snooze"):
        return jsonify({"error": "rating required and must be one of easy/medium/hard/snooze"}), 400
    
    song_id = data.get("song_id")
    measure_group_id = data.get("measure_group_id")
    if not song_id or not measure_group_id:
        return jsonify({"error": "song_id and measure_group_id required"}), 400

    # Optional fields
    duration_seconds = data.get("duration_seconds")
    notes = data.get("notes")
    
    db = get_db()
    cur = db.execute(
        "INSERT INTO practice_sessions (song_id, measure_group_id, rating, duration_seconds, notes) VALUES (?, ?, ?, ?, ?)",
        (song_id, measure_group_id, rating, duration_seconds, notes),
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
    """Return all practice sessions with song and measure info"""
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
    """Clear all practice session history"""
    db = get_db()
    db.execute("DELETE FROM practice_sessions")
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
    best_rating: int
    practice_count: int
    last_practiced: Optional[str]
    category: str

    # Add rating scores as class variable
    RATING_SCORES = {
        'easy': 3,
        'medium': 2,
        'hard': 1,
        'snooze': 0
    }
    
    @property
    def is_group(self) -> bool:
        return self.start != self.end
    
    @classmethod
    def from_db_row(cls, row: sqlite3.Row, ratings: List[str]) -> 'MeasureItem':
        best_rating = max((cls.RATING_SCORES[r] for r in ratings), default=0)
        category = (
            'proficient' if best_rating >= 3
            else 'decent' if best_rating >= 2
            else 'needs_practice' if best_rating >= 1
            else 'unlearned'
        )
        
        return cls(
            id=row['id'],
            start=row['start_measure'],
            end=row['end_measure'],
            best_rating=best_rating,
            practice_count=row['practice_count'] or 0,
            last_practiced=row['last_practiced'],
            category=category
        )

def get_next_measure(song_id: int):
    """Get next measure to practice using spaced repetition algorithm"""
    db = get_db()
    
    # Get song info
    song = db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not song:
        return jsonify({"error": "Song not found"}), 404

    measures = get_all_measures(db, song_id)
    if not measures:
        return jsonify({"measure": 1})
        
    eligible_items = get_eligible_items(measures)
    if not eligible_items:
        return jsonify({"measure": 1})
        
    next_item = select_next_item(eligible_items)
    return create_response(next_item)

@app.route("/api/songs/<int:song_id>/next-measure", methods=["GET"])
def next_measure_for_song(song_id: int):
    """Get next measure to practice for a specific song using spaced repetition"""
    return get_next_measure(song_id)

def get_all_measures(db, song_id: int) -> Dict[str, List[MeasureItem]]:
    """Get all measures and their practice history"""
    query = """
    SELECT 
        mg.id, mg.start_measure, mg.end_measure,
        GROUP_CONCAT(ps.rating) as ratings,
        COUNT(ps.id) as practice_count,
        MAX(ps.practiced_at) as last_practiced
    FROM measure_groups mg
    LEFT JOIN practice_sessions ps ON mg.id = ps.measure_group_id
    WHERE mg.song_id = ?
    GROUP BY mg.id, mg.start_measure, mg.end_measure
    ORDER BY mg.start_measure, mg.end_measure
    """
    
    rows = db.execute(query, (song_id,)).fetchall()
    single_measures = []
    measure_groups = []
    
    for row in rows:
        ratings = row['ratings'].split(',') if row['ratings'] else []
        item = MeasureItem.from_db_row(row, ratings)
        
        if item.is_group:
            measure_groups.append(item)
        else:
            single_measures.append(item)  # Uncommented and properly indented
            
    return {'single': single_measures, 'groups': measure_groups}

def get_eligible_items(measures: Dict[str, List[MeasureItem]]) -> List[MeasureItem]:
    """Determine which items are eligible for practice"""
    single_measures = measures['single']
    measure_groups = measures['groups']
    
    # Find current learning window
    window_size = 1
    max_measure = 1
    
    while window_size <= len(single_measures):
        current_window = single_measures[:window_size]
        current_groups = [
            g for g in measure_groups 
            if g.start >= 1 and g.end <= window_size
        ]
        
        if (all(m.category == 'proficient' for m in current_window) and 
            all(g.category == 'proficient' for g in current_groups)):
            window_size += 1
            max_measure = window_size
        else:
            break
    
    # Get eligible items within window
    eligible_items = []
    
    # Add non-proficient single measures
    window_measures = [m for m in single_measures if m.start <= max_measure]
    eligible_items.extend([m for m in window_measures if m.category != 'proficient'])
    
    # If all singles proficient, add non-proficient groups
    if not eligible_items:
        window_groups = [g for g in measure_groups if g.start >= 1 and g.end <= max_measure]
        eligible_items.extend([g for g in window_groups if g.category != 'proficient'])
    
    # If everything proficient, add next measure
    if not eligible_items and max_measure < len(single_measures):
        eligible_items.append(single_measures[max_measure])
        
    return eligible_items

def select_next_item(eligible_items: List[MeasureItem]) -> MeasureItem:
    """Select next item using weighted random selection"""
    categorized = {
        ProficiencyLevel.PROFICIENT: [m for m in eligible_items if m.category == 'proficient'],
        ProficiencyLevel.DECENT: [m for m in eligible_items if m.category == 'decent'],
        ProficiencyLevel.NEEDS_PRACTICE: [m for m in eligible_items if m.category == 'needs_practice'],
        ProficiencyLevel.UNLEARNED: [m for m in eligible_items if m.category == 'unlearned']
    }
    
    roll = random.random()
    
    if roll < 0.15 and categorized[ProficiencyLevel.PROFICIENT]:
        return random.choice(categorized[ProficiencyLevel.PROFICIENT])
    elif roll < 0.45 and categorized[ProficiencyLevel.DECENT]:
        return random.choice(categorized[ProficiencyLevel.DECENT])
    
    return min(eligible_items, key=lambda m: (
        {'unlearned': 0, 'needs_practice': 1, 'decent': 2, 'proficient': 3}[m.category],
        m.practice_count,
        m.start
    ))

def create_response(item: MeasureItem) -> Response:
    """Create JSON response for selected item"""
    return jsonify({
        "id": item.id,  
        "stats": {
            "category": item.category,
            "best_rating": item.best_rating,
            "practice_count": item.practice_count,
            "last_practiced": item.last_practiced,
            "is_group": item.is_group
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)