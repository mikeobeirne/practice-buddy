"""
Split all MusicXML/MXL files in the data directory into individual measure files.
Each song gets its own subdirectory containing the original file and measure files.
"""
import logging
from pathlib import Path
from music21 import converter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def normalize_name(filename: str) -> str:
    """Convert filename to folder name, stripping extension and special chars"""
    base = Path(filename).stem
    return base.lower().replace(" ", "-")


def split_song(input_path: Path):
    """Split a song file into individual measure files in a subdirectory"""
    # Create song directory using normalized name
    song_dir = input_path.parent / normalize_name(input_path.name)
    song_dir.mkdir(exist_ok=True)

    # Parse score
    logging.info("Parsing %s", input_path)
    score = converter.parse(str(input_path))

    # Copy original file to song directory
    dest_song = song_dir / input_path.name
    if not dest_song.exists():
        score.write(fp=str(dest_song))

    # Extract each measure
    measure_count = 0
    for num in range(1, len(score.measureNumbers) + 1):
        out_path = song_dir / f"measure_{num}.musicxml"
        if out_path.exists():
            logging.info("Skipping existing %s", out_path)
            measure_count += 1
            continue

        try:
            measure = score.measures(num, num)
            if not measure or not measure.parts:
                logging.warning("No content in measure %s", num)
                continue

            measure.write("musicxml", fp=str(out_path))
            logging.info("Created %s", out_path)
            measure_count += 1

        except Exception as e:
            logging.error("Failed to process measure %s: %s", num, e)

    return measure_count


def main():
    # Always use the frontend data directory
    data_dir = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data"

    # Process all .mxl and .musicxml files that aren't inside song subdirectories
    music_files = []
    for ext in ["*.mxl", "*.musicxml"]:
        music_files.extend(data_dir.glob(ext))

    for file_path in music_files:
        if "_measure_" not in file_path.name:  # skip any existing measure files
            try:
                count = split_song(file_path)
                logging.info("Processed %s: %d measures", file_path.name, count)
            except Exception as e:
                logging.error("Failed to process %s: %s", file_path.name, e)


if __name__ == "__main__":
    main()