"""
Split an input .mxl (or other MusicXML) file into one .mxl file per measure.

Usage:
  python split_mxl.py path/to/input.mxl path/to/output_dir
"""
import argparse
import logging
import os
from music21 import converter, stream

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def collect_measure_numbers(score: stream.Score):
    nums = set()
    for part in score.parts:
        for m in part.getElementsByClass(stream.Measure):
            if m.number is not None:
                nums.add(m.number)
    # fallback: try to collect from top-level measures if none found
    if not nums:
        for m in score.getElementsByClass(stream.Measure):
            if m.number is not None:
                nums.add(m.number)
    return sorted(nums)


def split_mxl(input_path: str, out_dir: str, fmt: str = "musicxml", overwrite: bool = False):
    """
    Split input MusicXML or MXL into one file per measure.

    Default output format changed to 'musicxml' and output files will use the .musicxml extension.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    os.makedirs(out_dir, exist_ok=True)

    logging.info("Parsing %s", input_path)
    score = converter.parse(input_path)

    measure_numbers = collect_measure_numbers(score)
    if not measure_numbers:
        logging.warning("No measure numbers found; attempting to split by sequential measure index.")
        # try using measure indices if no explicit numbers
        all_measures = list(score.getElementsByClass(stream.Measure))
        measure_numbers = list(range(1, len(all_measures) + 1))

    base = os.path.splitext(os.path.basename(input_path))[0]

    # map chosen format to file extension
    ext = "musicxml" if fmt == "musicxml" else ("mxl" if fmt == "mxl" else fmt)

    for num in measure_numbers:
        try:
            sub = score.measures(num, num)
            if sub is None or len(sub.parts) == 0:
                logging.warning("No content for measure %s — skipping", num)
                continue
            out_name = f"{base}_measure_{num}.{ext}"
            out_path = os.path.join(out_dir, out_name)
            if os.path.exists(out_path) and not overwrite:
                logging.info("Skipping existing file %s", out_path)
                continue
            logging.info("Writing measure %s -> %s", num, out_path)
            sub.write(fmt, fp=out_path)
        except Exception as e:
            logging.error("Failed to write measure %s: %s", num, e)


def main():
    parser = argparse.ArgumentParser(description="Split a .mxl/.musicxml file into per-measure files.")
    parser.add_argument("input", help="Path to input .mxl or .xml file")
    parser.add_argument("outdir", help="Output directory for per-measure files")
    parser.add_argument("--format", choices=["mxl", "musicxml"], default="musicxml", help="Output format (default: musicxml)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    split_mxl(args.input, args.outdir, fmt=args.format, overwrite=args.overwrite)


if __name__ == "__main__":
    main()