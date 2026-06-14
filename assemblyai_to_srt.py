import argparse
import json
from pathlib import Path


PUNCTUATION_BREAKS = (".", "?", "!")
TRAILING_PUNCTUATION = ".,!?;:"


def format_timestamp(ms):
    ms = max(0, int(round(ms)))
    hours = ms // 3_600_000
    ms -= hours * 3_600_000
    minutes = ms // 60_000
    ms -= minutes * 60_000
    seconds = ms // 1_000
    ms -= seconds * 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def clean_word(text):
    text = text.strip().replace("—", "")
    text = text.strip("'\"“”‘’")
    return text.rstrip(TRAILING_PUNCTUATION)


def display_text(words):
    return " ".join(clean_word(word["text"]) for word in words).strip()


def output_text(words):
    text = display_text(words)
    if not text:
        return text
    return text[0].upper() + text[1:]


def has_terminal_punctuation(text):
    return text.strip().rstrip("'\"“”‘’").endswith(PUNCTUATION_BREAKS)


def normalized_word(word, max_word_duration_ms):
    start = int(word.get("start") or 0)
    end = int(word.get("end") or start)
    text = word.get("text") or ""

    if end < start:
        end = start

    duration = end - start
    if duration > max_word_duration_ms:
        estimated = max(240, min(max_word_duration_ms, 180 + len(clean_word(text)) * 90))
        end = start + estimated

    if end == start:
        end = start + 80

    new_word = dict(word)
    new_word["start"] = start
    new_word["end"] = end
    return new_word


def normalize_words(words, max_word_duration_ms):
    normalized = []
    for word in words:
        text = clean_word(word.get("text") or "")
        if not text:
            continue
        normalized.append(normalized_word(word, max_word_duration_ms))
    return normalized


def should_break(current, next_word, max_chars, max_words, max_duration_ms, gap_ms):
    previous = current[-1]
    current_text = display_text(current)
    next_text = clean_word(next_word["text"])
    projected = f"{current_text} {next_text}".strip()
    projected_duration = next_word["end"] - current[0]["start"]
    pause = next_word["start"] - previous["end"]
    previous_text = previous.get("text", "").strip()

    if pause > gap_ms:
        return True
    if len(projected) > max_chars:
        return True
    if len(current) >= max_words:
        return True
    if projected_duration > max_duration_ms:
        return True
    if has_terminal_punctuation(previous_text):
        return True
    if previous_text.endswith(",") and len(current) <= 2:
        return True

    return False


def build_segments(
    words,
    max_chars=40,
    max_words=7,
    max_duration_ms=2800,
    gap_ms=500,
    max_word_duration_ms=1200,
):
    words = normalize_words(words, max_word_duration_ms)
    segments = []
    current = []

    def flush():
        nonlocal current
        text = output_text(current)
        if text:
            segments.append((current[0]["start"], current[-1]["end"], text))
        current = []

    for word in words:
        if current and should_break(
            current,
            word,
            max_chars,
            max_words,
            max_duration_ms,
            gap_ms,
        ):
            flush()
        current.append(word)

    if current:
        flush()

    previous_end = 0
    adjusted_segments = []
    for start, end, text in segments:
        start = max(start, previous_end)
        if end <= start:
            end = start + 80
        adjusted_segments.append((start, end, text))
        previous_end = end

    return adjusted_segments


def write_srt(segments, output_path):
    with open(output_path, "w", encoding="utf-8") as output_file:
        for index, (start, end, text) in enumerate(segments, start=1):
            output_file.write(f"{index}\n")
            output_file.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            output_file.write(f"{text}\n\n")


def translate_srt(input_srt, output_srt, target_lang="zh-TW"):
    from googlecloud import GoogleTranslator

    translator = GoogleTranslator(source="en", target=target_lang)
    if translator.client is None:
        raise RuntimeError("Google Translate client is not initialized")

    translated_path = translator.translate_file(input_srt, output_file=str(output_srt))
    if translated_path is None or not Path(translated_path).exists():
        raise RuntimeError(f"Translation output was not created: {output_srt}")


def process_file(
    input_json,
    output_srt,
    max_chars=40,
    max_words=7,
    max_duration_ms=2800,
    gap_ms=500,
    max_word_duration_ms=1200,
    translate=False,
    target_lang="zh-TW",
):
    with open(input_json, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)

    words = data.get("words") or []
    segments = build_segments(
        words,
        max_chars=max_chars,
        max_words=max_words,
        max_duration_ms=max_duration_ms,
        gap_ms=gap_ms,
        max_word_duration_ms=max_word_duration_ms,
    )
    write_srt(segments, output_srt)

    translated_srt = None
    if translate:
        translated_srt = Path(output_srt).with_name("result-zh.srt")
        translate_srt(output_srt, translated_srt, target_lang=target_lang)

    return len(segments), translated_srt


def process_root(root_dir, **options):
    root = Path(root_dir)
    count = 0

    for input_json in sorted(root.glob("*/assemblyAI.json")):
        output_srt = input_json.with_name("result.srt")
        segment_count, translated_srt = process_file(input_json, output_srt, **options)
        print(f"Wrote {segment_count:3d} subtitles: {output_srt}")
        if translated_srt:
            print(f"Wrote translated subtitles: {translated_srt}")
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert AssemblyAI raw JSON word timestamps into short-form SRT "
            "subtitles close to scribo.srt granularity."
        )
    )
    parser.add_argument(
        "root_dir",
        help="Folder containing clip subfolders with assemblyAI.json files",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=40,
        help="Maximum characters per subtitle (default: 40)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=7,
        help="Maximum words per subtitle (default: 7)",
    )
    parser.add_argument(
        "--max-duration-ms",
        type=int,
        default=2800,
        help="Maximum subtitle duration in milliseconds (default: 2800)",
    )
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=500,
        help="Break when pause between words exceeds this many ms (default: 500)",
    )
    parser.add_argument(
        "--max-word-duration-ms",
        type=int,
        default=1200,
        help="Cap anomalously long single-word timings (default: 1200)",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="Only write result.srt; skip Traditional Chinese result-zh.srt",
    )
    parser.add_argument(
        "--target-lang",
        default="zh-TW",
        help="Translation target language for result-zh.srt (default: zh-TW)",
    )

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
