import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whisper


class TestLocalWhisperCli(unittest.TestCase):
    def test_format_timestamp(self):
        self.assertEqual(whisper.format_timestamp(0), "00:00:00,000")
        self.assertEqual(whisper.format_timestamp(65.4321), "00:01:05,432")
        self.assertEqual(whisper.format_timestamp(3661.999), "01:01:01,999")

    def test_iter_word_subtitles_breaks_on_silence(self):
        segment = SimpleNamespace(
            start=0,
            end=4,
            text="hello world later",
            words=[
                SimpleNamespace(start=0.1, end=0.3, word=" hello"),
                SimpleNamespace(start=0.3, end=0.6, word=" world"),
                SimpleNamespace(start=2.0, end=2.4, word=" later"),
            ],
        )

        subtitles = list(
            whisper.iter_word_subtitles(
                [segment],
                max_chars=42,
                max_duration=3,
                gap_threshold=0.5,
            )
        )

        self.assertEqual(
            subtitles,
            [
                (0.1, 0.6, "hello world"),
                (2.0, 2.4, "later"),
            ],
        )

    @patch("whisper.WhisperModel")
    def test_transcribe_to_srt_writes_segments(self, mock_model_class):
        segment = SimpleNamespace(
            start=1.2,
            end=3.4,
            text=" hello --> world ",
            words=[
                SimpleNamespace(start=1.2, end=1.8, word=" hello"),
                SimpleNamespace(start=1.8, end=3.4, word=" --> world"),
            ],
        )
        info = SimpleNamespace(language="en", language_probability=0.99)
        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([segment], info)

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "audio.wav")
            output_path = os.path.join(tmp_dir, "out.srt")
            with open(input_path, "wb") as audio_file:
                audio_file.write(b"test")

            result = whisper.transcribe_to_srt(
                input_path,
                output_file=output_path,
                model_size="tiny",
                device="cpu",
                compute_type="int8",
                language="en",
                beam_size=1,
                vad_filter=False,
            )

            self.assertEqual(result, output_path)
            mock_model_class.assert_called_once_with(
                "tiny",
                device="cpu",
                compute_type="int8",
            )
            mock_model.transcribe.assert_called_once_with(
                input_path,
                beam_size=1,
                language="en",
                vad_filter=False,
                word_timestamps=True,
            )

            with open(output_path, "r", encoding="utf-8") as srt_file:
                self.assertEqual(
                    srt_file.read(),
                    "1\n00:00:01,200 --> 00:00:03,400\nhello -> world\n\n",
                )


if __name__ == "__main__":
    unittest.main()
