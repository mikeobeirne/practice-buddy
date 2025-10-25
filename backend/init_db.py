import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "practice.db"
DATA_DIR = Path(__file__).parent.parent / "frontend" / "public" / "data"

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize database schema"""
    # Use the passed db connection instead of creating a new one
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS songs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      composer TEXT,
      source_file TEXT,
      total_measures INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS measure_groups (
      id TEXT PRIMARY KEY,  -- Changed to TEXT
      song_id INTEGER NOT NULL,
      start_measure INTEGER NOT NULL,
      end_measure INTEGER NOT NULL,
      created_at TEXT DEFAULT (datetime('now')),
      group_size INTEGER GENERATED ALWAYS AS (end_measure - start_measure + 1) VIRTUAL,
      FOREIGN KEY (song_id) REFERENCES songs(id)
    );

    CREATE TABLE IF NOT EXISTS practice_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      song_id INTEGER NOT NULL,
      measure_group_id TEXT NOT NULL,  -- Changed to TEXT
      practiced_at TEXT DEFAULT (datetime('now')),
      rating TEXT CHECK (rating IN ('easy','medium','hard','snooze')) NOT NULL,
      duration_seconds INTEGER,
      notes TEXT,
      FOREIGN KEY (song_id) REFERENCES songs(id),
      FOREIGN KEY (measure_group_id) REFERENCES measure_groups(id)
    );
    """)
    db.commit()
    return db

def scan_data_dir():
    """Scan data directory for songs and their measures"""
    songs = []
    measure_groups = []

    # Look for song folders
    for entry in os.scandir(DATA_DIR):
        if not entry.is_dir():
            continue
        
        print(f"Checking directory: {entry.path}")
        
        # Find the main song file (should match folder name)
        song_files = []
        for pattern in ["*.musicxml", "*.mxl"]:
            song_files.extend(Path(entry.path).glob(pattern))
        
        print(f"Found files: {song_files}")
        
        song_file = next((f for f in song_files if "measure_" not in f.name and "measures_" not in f.name), None)
        if not song_file:
            print(f"No main song file found in {entry.path}")
            continue

        # Find all measure files (single and multi-measure groups)
        all_measure_files = sorted(
            [f for f in Path(entry.path).glob("*.musicxml") if "measure_" in f.name or "measures_" in f.name],
            key=lambda p: (
                # Sort by start measure, then by length of range
                int(p.name.split("measure")[1].split("_")[1].split("-")[0].split(".")[0]),
                len(p.name.split("-")) if "-" in p.name else 0
            )
        )
        
        # Count single measures only for total_measures
        single_measures = [f for f in all_measure_files if "measure_" in f.name and "-" not in f.name]
        
        if single_measures:
            songs.append({
                'title': entry.name.replace('-', ' ').title(),
                'source_file': f"{entry.name}/{song_file.name}",
                'total_measures': len(single_measures)
            })
            
            # Create measure groups for all combinations
            for mf in all_measure_files:
                if "measure_" in mf.name and "-" not in mf.name:
                    # Single measure
                    measure = int(mf.name.split("measure_")[1].split(".")[0])
                    measure_groups.append((entry.name, measure, measure))
                elif "measures_" in mf.name:
                    # Multi-measure group
                    range_part = mf.name.split("measures_")[1].split(".")[0]
                    start, end = map(int, range_part.split("-"))
                    measure_groups.append((entry.name, start, end))

    return songs, measure_groups

def main():
    print(f"Scanning {DATA_DIR}")
    print(f"Path exists: {DATA_DIR.exists()}")
    print(f"Is directory: {DATA_DIR.is_dir()}")
    if DATA_DIR.exists():
        print("Contents:", list(DATA_DIR.iterdir()))
    
    songs, measure_groups = scan_data_dir()
    
    if not songs:
        print("No songs found!")
        return
    
    print(f"\nFound {len(songs)} songs:")
    for s in songs:
        print(f"- {s['title']} ({s['source_file']}) - {s['total_measures']} measures")
    
    # Count different types of measure groups
    single_measures = sum(1 for _, start, end in measure_groups if start == end)
    combined_measures = sum(1 for _, start, end in measure_groups if start != end)
    
    print(f"\nFound {single_measures} single measures and {combined_measures} measure combinations")
    print(f"Total measure groups: {len(measure_groups)}")
    
    if input("\nWrite to database? [y/N] ").lower() != 'y':
        return
    
    # Use init_db() to create schema
    db = init_db()
    
    # Insert songs, keeping track of inserted IDs
    song_ids = {}  # source_file -> id mapping
    for song in songs:
        cur = db.execute(
            "INSERT INTO songs (title, source_file, total_measures) VALUES (?, ?, ?)",
            (song['title'], song['source_file'], song['total_measures'])
        )
        db.commit()
        song_ids[song['source_file'].split('/')[0]] = cur.lastrowid
    
    # Insert measure groups
    for folder, start_measure, end_measure in measure_groups:
        song_id = song_ids.get(folder)
        if not song_id:
            print(f"Warning: no song found for measure in {folder}")
            continue
        
        # Construct the measure group ID
        if start_measure == end_measure:
            measure_id = f"{folder}|measure{start_measure}"
        else:
            measure_id = f"{folder}|measure{start_measure}-{end_measure}"
        
        db.execute(
            "INSERT INTO measure_groups (id, song_id, start_measure, end_measure) VALUES (?, ?, ?, ?)",
            (measure_id, song_id, start_measure, end_measure)
        )
    
    db.commit()
    print("Done!")

if __name__ == "__main__":
    main()