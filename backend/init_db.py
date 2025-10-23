import os
import sqlite3
import re
from pathlib import Path

# Config
DATA_DIR = Path("../frontend/public/data")
DB_PATH = Path("practice.db")

def init_tables(db):
    """Ensure tables exist"""
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
    """)
    db.commit()

def scan_data_dir():
    """Scan data directory for songs and measures"""
    songs = []
    measure_groups = []  # (song_base, measure_num) tuples

    for entry in os.scandir(DATA_DIR):
        if entry.is_file() and (entry.name.endswith('.musicxml') or entry.name.endswith('.mxl')):
            # top-level file = song
            base = Path(entry.name).stem
            if "_measure_" not in base:  # skip any top-level measure files
                songs.append({
                    'title': base.replace('-', ' ').title(),
                    'source_file': entry.name,
                    'total_measures': 0  # will update after scanning measures
                })

        elif entry.is_dir():
            # scan subdirectory for measure files
            measure_files = []
            for f in os.scandir(entry.path):
                if not f.is_file():
                    continue
                if not (f.name.endswith('.musicxml') or f.name.endswith('.mxl')):
                    continue
                m = re.search(r'_measure_(\d+)', f.name)
                if m:
                    measure_num = int(m.group(1))
                    measure_files.append((f.name, measure_num))
            
            if measure_files:
                # Create individual measure groups for each measure
                for _, measure in measure_files:
                    measure_groups.append((entry.name, measure))
                
                # update total_measures for the song
                max_measure = max(m for _, m in measure_files)
                for song in songs:
                    if song['source_file'].startswith(entry.name):
                        song['total_measures'] = max_measure

    return songs, measure_groups

def main():
    print(f"Scanning {DATA_DIR}")
    songs, measure_groups = scan_data_dir()
    
    if not songs:
        print("No songs found!")
        return
    
    print(f"\nFound {len(songs)} songs:")
    for s in songs:
        print(f"- {s['title']} ({s['source_file']}) - {s['total_measures']} measures")
    
    print(f"\nFound {len(measure_groups)} measure groups")
    
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
        song_ids[song['source_file']] = cur.lastrowid
    
    # Insert measure groups, linking to songs
    for folder, measure in measure_groups:
        # find matching song (where source_file starts with folder name)
        song_id = None
        for source_file, sid in song_ids.items():
            if source_file.startswith(folder):
                song_id = sid
                break
        
        if not song_id:
            print(f"Warning: no song found for measure {folder} measure {measure}")
            continue
        
        # Create single-measure group
        db.execute(
            "INSERT INTO measure_groups (song_id, start_measure, end_measure) VALUES (?, ?, ?)",
            (song_id, measure, measure)  # start and end are the same measure
        )
    
    db.commit()
    print("Done!")

if __name__ == '__main__':
    main()