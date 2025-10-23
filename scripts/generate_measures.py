import os
from pathlib import Path
import re
from music21 import converter, stream

def normalize_name(filename: str) -> str:
    """Convert filename to a normalized folder name"""
    # Remove extension
    base = Path(filename).stem
    # Convert spaces/special chars to dashes, lowercase
    normalized = re.sub(r'[^a-zA-Z0-9]+', '-', base).lower()
    # Remove leading/trailing dashes
    return normalized.strip('-')

def process_song(input_file: Path, output_dir: Path):
    """Process a single song file into measures
    Returns: (folder_name, number of measures)
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

    # Extract each measure
    measure_count = 0
    for num in range(1, total_measures + 1):
        out_path = measures_dir / f"measure_{num}.musicxml"
        if out_path.exists():
            print(f"Skipping existing {out_path}")
            measure_count += 1
            continue

        try:
            measure = score.measures(num, num)
            if not measure or not measure.parts:
                print(f"No content in measure {num}")
                continue

            measure.write("musicxml", fp=str(out_path))
            print(f"Created {out_path}")
            measure_count += 1

        except Exception as e:
            print(f"Failed to process measure {num}: {e}")

    return song_folder, measure_count

def main():
    # Always process files in frontend data directory
    input_dir = Path("../frontend/public/data")
    input_dir.mkdir(exist_ok=True)

    # Process all .mxl files first
    for f in input_dir.glob("*.mxl"):
        if "_measure_" not in f.name:  # skip any existing measure files
            print(f"Processing {f}")
            folder, count = process_song(f, input_dir)
            print(f"-> Created {folder}/ with {count} measures")

    # Then any standalone .musicxml files
    for f in input_dir.glob("*.musicxml"):
        if "_measure_" not in f.name:  # skip any existing measure files
            print(f"Processing {f}")
            folder, count = process_song(f, input_dir)
            print(f"-> Created {folder}/ with {count} measures")

if __name__ == "__main__":
    main()