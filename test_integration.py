import unittest
import os
import json
import shutil
import subprocess
from analyzer import analyze_video # This will fail if not defined yet

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_integration_output"
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        
        self.video_path = os.path.join(self.test_dir, "original.mp4")
        self.chat_path = os.path.join(self.test_dir, "original.mp4.rechat.json")
        
        # Create a dummy video file using ffmpeg (1 second)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=1",
            "-f", "lavfi", "-i", "sine=f=440:d=1",
            self.video_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Create a dummy rechat file
        rechat_data = [
            {"content_offset_seconds": 0.5, "message": {"body": "Pog"}}
        ]
        with open(self.chat_path, "w") as f:
            json.dump(rechat_data, f)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_analyze_video_integration(self):
        # This function should be called by twitch_download.py
        # Here we test it directly first
        analyze_video(self.video_path, self.chat_path)
        
        segments_path = os.path.join(self.test_dir, "segments.json")
        self.assertTrue(os.path.exists(segments_path), "segments.json should be created")
        
        with open(segments_path, "r") as f:
            segments = json.load(f)
            self.assertIsInstance(segments, list)
            # Since it's only 1 second, it might not find any "peaks" if the rolling average logic
            # requires more data, but we can check if it at least runs without error
            # and produces a valid json list.

if __name__ == "__main__":
    unittest.main()
