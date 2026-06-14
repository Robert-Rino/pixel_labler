import argparse
import html
import os
import sys

import srt
from google.cloud import translate_v2 as translate


class GoogleTranslator:
    """
    Small Google Cloud Translation API v2 wrapper.

    SRT translation is intentionally one-to-one: each subtitle block is
    translated independently and written back with the exact same index and
    timestamps.
    """

    def __init__(self, source="auto", target="zh-TW"):
        self.source = source
        self.target = target
        try:
            self.client = translate.Client()
        except Exception as exc:
            print(
                f"Failed to initialize Google Translate Client: {exc}",
                file=sys.stderr,
            )
            self.client = None

    def translate(self, text, target=None):
        if not text:
            return ""

        if self.client is None:
            print("Google Translate Client not initialized.", file=sys.stderr)
            return text

        target_lang = target or self.target
        try:
            result = self.client.translate(
                text,
                target_language=target_lang,
                source_language=self._source_language(),
            )
        except Exception as exc:
            print(f"Translation failed: {exc}", file=sys.stderr)
            return text

        return html.unescape(result["translatedText"])

    def translate_lines(self, texts, target=None, max_chars=4500, max_items=128):
        """
        Translate a list while preserving one output per input.

        This batches requests for speed, but does not join neighboring lines or
        give the model cross-line context. That keeps subtitle ordering stable.
        """
        translated = [""] * len(texts)

        for chunk_indexes in self._chunk_indexes(texts, max_chars, max_items):
            chunk = [texts[index] for index in chunk_indexes]
            chunk_translations = self._translate_batch(chunk, target=target)

            for index, text, translation in zip(
                chunk_indexes, chunk, chunk_translations
            ):
                translated[index] = translation.strip() or text

        return translated

    def translate_file(self, input_file, output_file="zh.srt"):
        input_path = os.path.abspath(input_file)
        output_path = self._resolve_output_path(input_path, output_file)

        print(f"Translating {input_path} -> {output_path} ({self.target})...")

        with open(input_path, "r", encoding="utf-8") as source_file:
            content = source_file.read()

        try:
            subtitles = list(srt.parse(content))
        except srt.SRTParseError as exc:
            print(f"Error parsing SRT file: {exc}", file=sys.stderr)
            return None

        texts = [subtitle.content for subtitle in subtitles]
        translated_texts = self.translate_lines(texts)

        with open(output_path, "w", encoding="utf-8") as translated_file:
            for subtitle, text in zip(subtitles, translated_texts):
                translated_file.write(f"{subtitle.index}\n")
                translated_file.write(
                    f"{self._format_time(subtitle.start)} --> "
                    f"{self._format_time(subtitle.end)}\n"
                )
                translated_file.write(f"{text}\n\n")

        return output_path

    def _source_language(self):
        if self.source == "auto":
            return None
        return self.source

    def _translate_batch(self, texts, target=None):
        if not texts:
            return []

        if self.client is None:
            print("Google Translate Client not initialized.", file=sys.stderr)
            return texts

        try:
            results = self.client.translate(
                texts,
                target_language=target or self.target,
                source_language=self._source_language(),
            )
        except Exception as exc:
            print(f"Batch translation failed: {exc}", file=sys.stderr)
            return [self.translate(text, target=target) for text in texts]

        if isinstance(results, dict):
            results = [results]

        return [html.unescape(result["translatedText"]) for result in results]

    def _chunk_indexes(self, texts, max_chars, max_items):
        chunk = []
        chunk_len = 0

        for index, text in enumerate(texts):
            text_len = max(1, len(text))
            if chunk and (len(chunk) >= max_items or chunk_len + text_len > max_chars):
                yield chunk
                chunk = []
                chunk_len = 0

            chunk.append(index)
            chunk_len += text_len

        if chunk:
            yield chunk

    @staticmethod
    def _resolve_output_path(input_path, output_file):
        if os.path.isabs(output_file):
            return output_file

        if os.path.dirname(output_file):
            return os.path.abspath(output_file)

        return os.path.join(os.path.dirname(input_path), output_file)

    @staticmethod
    def _format_time(value):
        total_ms = max(0, round(value.total_seconds() * 1000))
        hours = total_ms // 3_600_000
        total_ms -= hours * 3_600_000
        minutes = total_ms // 60_000
        total_ms -= minutes * 60_000
        seconds = total_ms // 1_000
        total_ms -= seconds * 1_000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{total_ms:03d}"


def main():
    parser = argparse.ArgumentParser(description="Google Cloud Translate CLI")
    parser.add_argument("text", help="Text to translate OR path to .srt file")
    parser.add_argument(
        "-t",
        "--target",
        default="zh-TW",
        help="Target language code (default: zh-TW)",
    )
    parser.add_argument(
        "-s",
        "--source",
        default="auto",
        help="Source language code (default: auto)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="zh.srt",
        help="Output path for SRT translation (default: zh.srt beside input)",
    )

    args = parser.parse_args()
    translator = GoogleTranslator(source=args.source, target=args.target)

    if os.path.isfile(args.text):
        if args.text.lower().endswith(".srt"):
            translator.translate_file(args.text, output_file=args.output)
            return

        with open(args.text, "r", encoding="utf-8") as input_file:
            print(translator.translate(input_file.read()))
            return

    print(translator.translate(args.text))


if __name__ == "__main__":
    main()
