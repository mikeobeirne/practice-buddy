from flask import Flask, request, jsonify, g
from flask_cors import CORS
import sqlite3
import os
from typing import List

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


@app.route("/api/songs", methods=["POST"])
def create_song():
    data = request.get_json() or {}
    title = data.get("title")
    if not title:
        return jsonify({"error": "title required"}), 400
    composer = data.get("composer")
    source_file = data.get("source_file")
    total_measures = int(data.get("total_measures") or 0)
    db = get_db()
    cur = db.execute(
        "INSERT INTO songs (title, composer, source_file, total_measures) VALUES (?, ?, ?, ?)",
        (title, composer, source_file, total_measures),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/measure-groups", methods=["POST"])
def create_measure_group():
    data = request.get_json() or {}
    song_id = data.get("song_id")
    start = int(data.get("start_measure") or 0)
    end = int(data.get("end_measure") or 0)
    if not song_id or start < 1 or end < start:
        return jsonify({"error": "invalid payload"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO measure_groups (song_id, start_measure, end_measure) VALUES (?, ?, ?)",
        (song_id, start, end),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/practice", methods=["POST"])
def log_practice():
    data = request.get_json() or {}
    rating = data.get("rating") or data.get("difficulty")
    if rating not in ("easy", "medium", "hard", "snooze"):
        return jsonify({"error": "rating required and must be one of easy/medium/hard/snooze"}), 400
    song_id = data.get("song_id")
    measure_group_id = data.get("measure_group_id")
    duration_seconds = data.get("duration_seconds")
    notes = data.get("notes")
    # accept fallback payloads where client only sends filename/measure/measureId:
    filename = data.get("filename")
    measure = data.get("measure")
    measureId = data.get("measureId")
    db = get_db()

    # If song_id/measure_group_id provided, use them directly.
    if not song_id or not measure_group_id:
        # try best-effort mapping: if filename present, try to find song by matching source_file basename
        if filename:
            # try to find song where source_file basename is prefix of filename
            fname = os.path.basename(filename)
            base_candidate = os.path.splitext(fname)[0].split("_measure_")[0]
            row = db.execute("SELECT * FROM songs WHERE source_file LIKE ? LIMIT 1", (f"%{base_candidate}%",)).fetchone()
            if row:
                song_id = row["id"]
        # if measureId provided (e.g. "3_4_5"), try to find matching measure_group by exact string in notes? (not implemented)
        # if measure provided and song_id found, try to find a measure_group that contains that measure
        if song_id and measure:
            mg = db.execute(
                "SELECT * FROM measure_groups WHERE song_id = ? AND start_measure <= ? AND end_measure >= ? LIMIT 1",
                (song_id, measure, measure),
            ).fetchone()
            if mg:
                measure_group_id = mg["id"]

    if not song_id or not measure_group_id:
        return jsonify({"error": "song_id and measure_group_id required (or provide filename/measure that can be resolved)"}), 400

    cur = db.execute(
        "INSERT INTO practice_sessions (song_id, measure_group_id, rating, duration_seconds, notes) VALUES (?, ?, ?, ?, ?)",
        (song_id, measure_group_id, rating, duration_seconds, notes),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/next", methods=["GET"])
def next_to_practice():
    """
    Returns an ordered list of filenames (strings). Strategy:
      - consider all measure_groups (optionally filtered by song_id or prefix)
      - compute practice count per group (practice_sessions)
      - sort by fewest practice count, then older groups first
      - return filenames constructed from song.source_file + measure start
    Query params:
      song_id (optional)
      limit (optional, default 10)
    """
    limit = int(request.args.get("limit", 10))
    song_id_filter = request.args.get("song_id")

    db = get_db()

    params = []
    q = """
    SELECT mg.*, s.source_file,
      (SELECT COUNT(*) FROM practice_sessions ps WHERE ps.measure_group_id = mg.id) AS practice_count
    FROM measure_groups mg
    JOIN songs s ON s.id = mg.song_id
    """
    if song_id_filter:
        q += " WHERE mg.song_id = ?"
        params.append(song_id_filter)
    q += " ORDER BY practice_count ASC, mg.created_at ASC LIMIT ?"
    params.append(limit)

    rows = db.execute(q, params).fetchall()

    filenames: List[str] = []
    for r in rows:
        # prefer returning the start_measure file for the group
        start = r["start_measure"]
        song_row = r
        candidates = file_candidates_from_song_and_measure(song_row, start)
        # return first candidate (musicxml) — client can try that path
        filenames.append(candidates[0])
    return jsonify(filenames)


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


@app.route("/api/songs/<int:song_id>/next-measure", methods=["GET"])
def get_next_measure(song_id):
    """Get the next measure using spaced repetition approach."""
    db = get_db()
    
    # Define rating scores
    rating_scores = {
        'easy': 3,
        'medium': 2,
        'hard': 1,
        'snooze': 0
    }
    
    # Get song info
    song = db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not song:
        return jsonify({"error": "Song not found"}), 404

    # Get all measures and their practice history
    measures_query = """
    SELECT 
        mg.start_measure,
        GROUP_CONCAT(ps.rating) as ratings,
        COUNT(ps.id) as practice_count,
        MAX(ps.practiced_at) as last_practiced
    FROM measure_groups mg
    LEFT JOIN practice_sessions ps ON mg.id = ps.measure_group_id
    WHERE mg.song_id = ?
    GROUP BY mg.start_measure
    ORDER BY mg.start_measure
    """
    
    rows = db.execute(measures_query, (song_id,)).fetchall()
    
    # Process each measure's data
    measures = []
    for row in rows:
        ratings = row['ratings'].split(',') if row['ratings'] else []
        best_rating = max((rating_scores[r] for r in ratings), default=0)
        
        category = 'unlearned'
        if best_rating >= 3:
            category = 'proficient'
        elif best_rating >= 2:  # Changed: require medium (2) or better
            category = 'challenging'
        
        measures.append({
            'measure': row['start_measure'],
            'category': category,
            'best_rating': best_rating,
            'practice_count': row['practice_count'] or 0,
            'last_practiced': row['last_practiced']
        })

    # Find current learning window
    def is_measure_learned(m):
        return m['best_rating'] >= 2  # Changed: require medium (2) or better
    
    # Start with initial window of 5 measures
    window_size = 5
    
    # Check if we can expand window
    if len(measures) > window_size:
        current_window = measures[:window_size]
        learned_count = sum(1 for m in current_window if is_measure_learned(m))
        
        # Only expand if ALL measures up to current window are sufficiently learned
        if learned_count == window_size:
            window_size += 3  # Add next chunk
    
    # Cap window size at total measures
    window_size = min(len(measures), window_size)
    
    # Filter to measures in current window
    eligible_measures = measures[:window_size]
    
    if not eligible_measures:
        return jsonify({"measure": 1})
    
    # Prioritize unlearned and challenging measures in current window
    def measure_priority(m):
        category_score = {
            'unlearned': 0,
            'challenging': 1,
            'proficient': 2
        }[m['category']]
        
        # Prioritize earlier measures within same category
        return (
            category_score,
            m['practice_count'],
            m['measure']
        )
    
    next_measure = min(eligible_measures, key=measure_priority)
    
    return jsonify({
        "measure": next_measure['measure'],
        "stats": {
            "category": next_measure['category'],
            "best_rating": next_measure['best_rating'],
            "practice_count": next_measure['practice_count'],
            "last_practiced": next_measure['last_practiced']
        }
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)