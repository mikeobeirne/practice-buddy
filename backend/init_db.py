import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "practice.db"
DATA_DIR = Path(__file__).parent.parent / "frontend" / "public" / "data"

def init_tables(db):
    """Initialize fresh schema"""
    db.executescript("""
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
      group_size INTEGER GENERATED ALWAYS AS (end_measure - start_measure + 1) VIRTUAL,
      FOREIGN KEY (song_id) REFERENCES songs(id)
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
    """)
    db.commit()

def scan_data_dir():
    """Scan data directory for songs and their measures"""
    songs = []
    measure_groups = []

    # Look for song folders
    for entry in os.scandir(DATA_DIR):
        if not entry.is_dir():
            continue
        
        print(f"Checking directory: {entry.path}")  # Debug
        
        # Find the main song file (should match folder name)
        song_files = []
        for pattern in ["*.musicxml", "*.mxl"]:
            song_files.extend(Path(entry.path).glob(pattern))
        
        print(f"Found files: {song_files}")  # Debug
        
        # Find main song file (any file that isn't a measure file)
        song_file = next((f for f in song_files if "measure_" not in f.name), None)
        if not song_file:
            print(f"No main song file found in {entry.path}")  # Debug
            continue

        # Count measures by looking for measure_*.musicxml files
        measure_files = sorted(
            [f for f in Path(entry.path).glob("*.musicxml") if "measure_" in f.name],
            key=lambda p: int(p.name.split("measure_")[1].split(".")[0])
        )
        
        print(f"Found measures: {measure_files}")  # Debug
        
        if measure_files:
            songs.append({
                'title': entry.name.replace('-', ' ').title(),
                'source_file': f"{entry.name}/{song_file.name}",
                'total_measures': len(measure_files)
            })
            
            # Create individual measure groups
            for mf in measure_files:
                measure = int(mf.name.split("measure_")[1].split(".")[0])
                measure_groups.append((entry.name, measure))

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
    
    print(f"\nFound {len(measure_groups)} individual measures")
    
    if input("\nWrite to database? [y/N] ").lower() != 'y':
        return
    
    db = sqlite3.connect(DB_PATH)
    init_tables(db)
    
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
    for folder, measure in measure_groups:
        song_id = song_ids.get(folder)
        if not song_id:
            print(f"Warning: no song found for measure in {folder}")
            continue
        
        db.execute(
            "INSERT INTO measure_groups (song_id, start_measure, end_measure) VALUES (?, ?, ?)",
            (song_id, measure, measure)
        )
    
    db.commit()
    print("Done!")

if __name__ == "__main__":
    main()