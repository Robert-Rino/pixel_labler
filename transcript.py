import os
import sys
import argparse
import json
from pathlib import Path
import assemblyai as aai

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


def to_srt(
    input_json,
    output_dir=None,
    max_chars=40,
    max_words=7,
    max_duration_ms=2800,
    gap_ms=500,
    max_word_duration_ms=1200,
    translate=True,
    target_lang="zh-TW",
):
    input_json = Path(input_json)
    output_dir = Path(output_dir) if output_dir else input_json.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_srt = output_dir / "result.srt"
    translated_srt = output_dir / "result-zh.srt"

    with open(input_json, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)

    segments = build_segments(
        data.get("words") or [],
        max_chars=max_chars,
        max_words=max_words,
        max_duration_ms=max_duration_ms,
        gap_ms=gap_ms,
        max_word_duration_ms=max_word_duration_ms,
    )

    write_srt(segments, output_srt)
    print(f"Wrote {len(segments):3d} subtitles: {output_srt}")

    if translate:
        translate_srt(output_srt, translated_srt, target_lang=target_lang)
        print(f"Wrote translated subtitles: {translated_srt}")
    else:
        translated_srt = None

    return output_srt, translated_srt, len(segments)


def transcribe_video(
    input_file: str,
    output_file: str,
    speaker_labels: bool = False,
    google_translate: bool = True,
    target_lang: str = "zh-TW",
):
    """
    Transcribe a video or audio file with AssemblyAI and write assemblyAI.json.
    
    Args:
        input_file: Path to the input video/audio file.
        output_file: Path used to determine the output directory.
        speaker_labels: Enable speaker diarization in AssemblyAI.
        google_translate: Write translated result-zh.srt when True.
        target_lang: Translation target language.
    """
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print("Error: ASSEMBLYAI_API_KEY environment variable not set.")
        sys.exit(1)
        
    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()
    config = dict(
        speech_models=["universal-3-pro", "universal-2"],
        format_text=True,
        punctuate=False,
        language_detection=True,
        disfluencies=True,
    )

    if speaker_labels:
        config["speaker_labels"] = True

    transcribe_config = aai.TranscriptionConfig(**config)
    
    print("Starting Analysis & Transcription (AssemblyAI)...")
    transcript = transcriber.transcribe(input_file, config=transcribe_config)
    
    if transcript.status == aai.TranscriptStatus.error:
        print(f"AssemblyAI Error: {transcript.error}")
        sys.exit(1)

    output_dir = os.path.dirname(os.path.abspath(output_file or input_file))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    json_output = os.path.join(output_dir, "assemblyAI.json")

    print(f"Writing AssemblyAI JSON to: {json_output}")
    with open(json_output, "w", encoding="utf-8") as json_file:
        json.dump(transcript.json_response, json_file, ensure_ascii=False, indent=2)

    to_srt(json_output, translate=google_translate, target_lang=target_lang)

    print("Done!")
    return json_output


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio/video and write AssemblyAI JSON")
    parser.add_argument("input_file", help="Path to input video/audio file")
    parser.add_argument("--speaker_labels", action="store_true", help="Enable speaker labels")
    parser.add_argument("--no-translate", action="store_true", help="Only write result.srt; skip result-zh.srt")
    parser.add_argument("--target-lang", default="zh-TW", help="Translation target language for result-zh.srt")

    args = parser.parse_args()
    input_file = os.path.abspath(args.input_file)

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
        
    # Use transcript.srt as a legacy path hint; AssemblyAI JSON is written beside it.
    original_output = os.path.join(os.path.dirname(input_file), "transcript.srt")
    try:
        transcribe_video(
            input_file=input_file,
            output_file=original_output,
            speaker_labels=args.speaker_labels,
            google_translate=not args.no_translate,
            target_lang=args.target_lang,
        )
    except Exception as e:
        print(f"Error during transcription: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
