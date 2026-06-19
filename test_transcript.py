import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import transcript


class TestTranscriptAssemblyAI(unittest.TestCase):
    @patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "test-key"})
    @patch("transcript.translate_srt")
    @patch("transcript.aai.TranscriptionConfig")
    @patch("transcript.aai.Transcriber")
    def test_assemblyai_transcribe_writes_json_and_srt_outputs(
        self,
        mock_transcriber_class,
        mock_config_class,
        mock_translate_srt,
    ):
        def fake_translate(input_srt, output_srt, target_lang="zh-TW"):
            with open(output_srt, "w", encoding="utf-8") as f:
                f.write("translated")

        mock_translate_srt.side_effect = fake_translate
        mock_transcript = SimpleNamespace(
            status="completed",
            error=None,
            json_response={
                "id": "abc",
                "text": "hello world",
                "words": [
                    {"text": "hello", "start": 0, "end": 500},
                    {"text": "world", "start": 550, "end": 1000},
                ],
            },
        )
        mock_transcriber_class.return_value.transcribe.return_value = mock_transcript

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "audio.wav")
            output_path = os.path.join(temp_dir, "transcript.srt")
            open(input_path, "wb").close()

            result = transcript.transcribe_video(
                input_file=input_path,
                output_file=output_path,
            )

            expected_json_path = os.path.join(temp_dir, "assemblyAI.json")
            expected_srt_path = os.path.join(temp_dir, "result.srt")
            expected_zh_srt_path = os.path.join(temp_dir, "result-zh.srt")
            self.assertEqual(result, expected_json_path)
            self.assertTrue(os.path.exists(expected_json_path))
            self.assertTrue(os.path.exists(expected_srt_path))
            self.assertTrue(os.path.exists(expected_zh_srt_path))

            with open(expected_json_path, "r", encoding="utf-8") as json_file:
                self.assertEqual(json.load(json_file), mock_transcript.json_response)
            with open(expected_srt_path, "r", encoding="utf-8") as srt_file:
                self.assertIn("Hello world", srt_file.read())
            with open(expected_zh_srt_path, "r", encoding="utf-8") as zh_srt_file:
                self.assertEqual(zh_srt_file.read(), "translated")

        mock_config_class.assert_called_once()
        config_kwargs = mock_config_class.call_args.kwargs
        self.assertEqual(config_kwargs["speech_models"], ["universal-3-pro", "universal-2"])
        mock_transcriber_class.return_value.transcribe.assert_called_once_with(
            input_path,
            config=mock_config_class.return_value,
        )
        mock_translate_srt.assert_called_once()


if __name__ == "__main__":
    unittest.main()
