import os
from pathlib import Path
import re
from music21 import converter, stream
from enum import Enum
from typing import Dict, List, Set, Tuple

def normalize_name(filename: str) -> str:
    """Convert filename to a normalized folder name"""
    # Remove extension
    base = Path(filename).stem
    # Convert spaces/special chars to dashes, lowercase
    normalized = re.sub(r'[^a-zA-Z0-9]+', '-', base).lower()
    # Remove leading/trailing dashes
    return normalized.strip('-')

def process_song(input_file: Path, output_dir: Path):
    """Process a single song file into measures and measure combinations
    Returns: (folder_name, number of single measures, number of combinations)
    """
    # Create normalized folder name from song file
    song_folder = normalize_name(input_file.name)
    measures_dir = output_dir / song_folder
    measures_dir.mkdir(exist_ok=True)

    # Parse score using music21
    print(f"Parsing {input_file}")
    score = converter.parse(str(input_file))

    # Copy original file to song directory
    dest_song = measures_dir / input_file.name
    if not dest_song.exists():
        score.write(fp=str(dest_song))

    # Get total measures using measureOffsetMap
    total_measures = len(score.parts[0].measureOffsetMap())
    print(f"Found {total_measures} measures")

    # Track counts for reporting
    single_count = 0
    combo_count = 0
    
    # Create normalized folder name for IDs
    song_id_prefix = normalize_name(input_file.name)

    # Extract single measures
    for num in range(1, total_measures + 1):
        measure_id = f"{song_id_prefix}|measure{num}"
        out_path = measures_dir / f"measure_{num}.musicxml"
        
        if out_path.exists():
            print(f"Skipping existing {out_path}")
            single_count += 1
            continue

        try:
            measure = score.measures(num, num)
            if not measure or not measure.parts:
                print(f"No content in measure {num}")
                continue

            measure.write("musicxml", fp=str(out_path))
            print(f"Created {out_path} with ID {measure_id}")
            single_count += 1

        except Exception as e:
            print(f"Failed to process measure {num}: {e}")

    # Generate 2-3 measure combinations
    for size in [2, 3]:
        for start in range(1, total_measures - size + 2):
            end = start + size - 1
            measure_id = f"{song_id_prefix}|measure{start}-{end}"
            out_path = measures_dir / f"measures_{start}-{end}.musicxml"
            
            if out_path.exists():
                print(f"Skipping existing {out_path}")
                combo_count += 1
                continue

            try:
                measures = score.measures(start, end)
                if not measures or not measures.parts:
                    print(f"No content in measures {start}-{end}")
                    continue

                measures.write("musicxml", fp=str(out_path))
                print(f"Created {out_path} with ID {measure_id}")
                combo_count += 1

            except Exception as e:
                print(f"Failed to process measures {start}-{end}: {e}")

    return song_folder, single_count, combo_count

def main():
    # Always process files in frontend data directory
    input_dir = Path("../frontend/public/data")
    input_dir.mkdir(exist_ok=True)

    # Process all .mxl files first
    for f in input_dir.glob("*.mxl"):
        if "_measure" not in f.name:  # skip any existing measure files
            print(f"Processing {f}")
            folder, singles, combos = process_song(f, input_dir)
            print(f"-> Created {folder}/ with {singles} single measures and {combos} combinations")

    # Then any standalone .musicxml files
    for f in input_dir.glob("*.musicxml"):
        if "_measure" not in f.name:  # skip any existing measure files
            print(f"Processing {f}")
            folder, singles, combos = process_song(f, input_dir)
            print(f"-> Created {folder}/ with {singles} single measures and {combos} combinations")

class ProficiencyLevel(Enum):
    PROFICIENT = 4
    DECENT = 3
    NEEDS_PRACTICE = 2
    UNLEARNED = 1

class MeasureGroup:
    def __init__(self, id: str, start: int, end: int):
        self.id = id
        self.start = start
        self.end = end
        self.best_rating = "unrated"
        self.all_ratings: List[str] = []
    
    @property
    def size(self) -> int:
        return self.end - self.start + 1
    
    @property
    def proficiency(self) -> ProficiencyLevel:
        if not self.all_ratings:
            return ProficiencyLevel.UNLEARNED
            
        if "hard" in self.all_ratings:
            return ProficiencyLevel.NEEDS_PRACTICE
            
        if all(r == "easy" for r in self.last_n_ratings(3)):
            return ProficiencyLevel.PROFICIENT
            
        if all(r in ["easy", "medium"] for r in self.last_n_ratings(2)):
            return ProficiencyLevel.DECENT
            
        return ProficiencyLevel.NEEDS_PRACTICE
    
    def last_n_ratings(self, n: int) -> List[str]:
        return self.all_ratings[-n:] if len(self.all_ratings) >= n else []

def get_measure_proficiencies(db, song_id: int) -> Dict[str, MeasureGroup]:
    """Get all measure groups and their practice history"""
    groups: Dict[str, MeasureGroup] = {}
    
    # First get all measure groups
    rows = db.execute("""
        SELECT id, start_measure, end_measure 
        FROM measure_groups 
        WHERE song_id = ?
    """, (song_id,)).fetchall()
    
    for row in rows:
        groups[row['id']] = MeasureGroup(row['id'], row['start_measure'], row['end_measure'])
    
    # Then get all practice history
    practice_rows = db.execute("""
        SELECT measure_group_id, rating 
        FROM practice_sessions 
        WHERE song_id = ?
        ORDER BY practiced_at ASC
    """, (song_id,)).fetchall()
    
    for row in practice_rows:
        if row['measure_group_id'] in groups:
            groups[row['measure_group_id']].all_ratings.append(row['rating'])
    
    return groups

def categorize_measures(groups: Dict[str, MeasureGroup]) -> Dict[ProficiencyLevel, Set[str]]:
    """Categorize measures into proficiency buckets"""
    buckets: Dict[ProficiencyLevel, Set[str]] = {
        level: set() for level in ProficiencyLevel
    }
    
    # First process multi-measure groups
    multi_measures = {id: group for id, group in groups.items() if group.size > 1}
    for id, group in multi_measures.items():
        # Check if component measures are decent
        component_measures = {
            mid: g for mid, g in groups.items() 
            if g.size == 1 and g.start >= group.start and g.end <= group.end
        }
        
        if all(m.proficiency >= ProficiencyLevel.DECENT for m in component_measures.values()):
            if group.proficiency == ProficiencyLevel.UNLEARNED:
                buckets[ProficiencyLevel.NEEDS_PRACTICE].add(id)
            else:
                buckets[group.proficiency].add(id)
    
    # Then process single measures
    single_measures = {id: group for id, group in groups.items() if group.size == 1}
    for id, group in single_measures.items():
        if group.proficiency == ProficiencyLevel.UNLEARNED:
            # Only add to NEEDS_PRACTICE if that bucket is empty
            if not buckets[ProficiencyLevel.NEEDS_PRACTICE]:
                buckets[ProficiencyLevel.NEEDS_PRACTICE].add(id)
            else:
                buckets[ProficiencyLevel.UNLEARNED].add(id)
        else:
            buckets[group.proficiency].add(id)
    
    return buckets

def get_next_measure(db, song_id: int) -> Tuple[str, ProficiencyLevel]:
    """Get the next measure to practice"""
    groups = get_measure_proficiencies(db, song_id)
    buckets = categorize_measures(groups)
    
    # Priority order for practice
    for level in [ProficiencyLevel.NEEDS_PRACTICE, ProficiencyLevel.UNLEARNED]:
        if buckets[level]:
            # Get the measure with fewest practices from this bucket
            measure_id = min(
                buckets[level],
                key=lambda id: len(groups[id].all_ratings)
            )
            return measure_id, level
    
    # If nothing needs practice, return random decent measure
    if buckets[ProficiencyLevel.DECENT]:
        return next(iter(buckets[ProficiencyLevel.DECENT])), ProficiencyLevel.DECENT
    
    # Otherwise return random proficient measure
    return next(iter(buckets[ProficiencyLevel.PROFICIENT])), ProficiencyLevel.PROFICIENT
