import argparse
from pathlib import Path

from transcript import to_srt


def process_root(root_dir, **options):
    root = Path(root_dir)
    count = 0

    for input_json in sorted(root.glob("*/assemblyAI.json")):
        to_srt(input_json, **options)
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Convert AssemblyAI JSON files into result.srt and result-zh.srt."
    )
    parser.add_argument("root_dir", help="Folder containing clip subfolders with assemblyAI.json files")
    parser.add_argument("--max-chars", type=int, default=40, help="Maximum characters per subtitle")
    parser.add_argument("--max-words", type=int, default=7, help="Maximum words per subtitle")
    parser.add_argument("--max-duration-ms", type=int, default=2800, help="Maximum subtitle duration")
    parser.add_argument("--gap-ms", type=int, default=500, help="Break when pause exceeds this many ms")
    parser.add_argument("--max-word-duration-ms", type=int, default=1200, help="Cap long word timings")
    parser.add_argument("--no-translate", action="store_true", help="Only write result.srt")
    parser.add_argument("--target-lang", default="zh-TW", help="Translation target language")

    args = parser.parse_args()
    processed = process_root(
        args.root_dir,
        max_chars=args.max_chars,
        max_words=args.max_words,
        max_duration_ms=args.max_duration_ms,
        gap_ms=args.gap_ms,
        max_word_duration_ms=args.max_word_duration_ms,
        translate=not args.no_translate,
        target_lang=args.target_lang,
    )

    if processed == 0:
        raise SystemExit(f"No assemblyAI.json files found under {args.root_dir}")


if __name__ == "__main__":
    main()
