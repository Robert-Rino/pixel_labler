import unittest
import os
import json
import shutil
import subprocess
import sys
from twitch_download import main as twitch_main

class TestE2EMocked(unittest.TestCase):
    def setUp(self):
        self.root_dir = "test_e2e_output"
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir)

    def tearDown(self):
        if os.path.exists(self.root_dir):
            shutil.rmtree(self.root_dir)

    def test_full_flow_with_preexisting_video(self):
        # We'll mock the parts that require internet
        import unittest.mock as mock
        
        with mock.patch('yt_dlp.YoutubeDL') as mock_ydl:
            # Mock metadata
            instance = mock_ydl.return_value.__enter__.return_value
            instance.extract_info.return_value = {
                'uploader': 'testuser',
                'upload_date': '20230101',
                'timestamp': 1672531200,
                'title': 'Test VOD',
                'description': 'Test Description',
                'duration': 60
            }
            
            date_str = "2023-01-01T08_00_00" 
            video_dir = os.path.join(self.root_dir, f"Twitch_VOD_testuser_{date_str}")
            os.makedirs(video_dir, exist_ok=True)
            
            # Create dummy original.mp4
            video_path = os.path.join(video_dir, "original.mp4")
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc=duration=5:size=160x120:rate=1",
                "-f", "lavfi", "-i", "sine=f=440:d=5",
                video_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            # Create dummy rechat.json
            chat_path = os.path.join(video_dir, "original.mp4.rechat.json")
            rechat_data = [
                {"content_offset_seconds": 1.0, "message": {"body": "Pog"}},
                {"content_offset_seconds": 2.0, "message": {"body": "KEKW"}},
                {"content_offset_seconds": 3.0, "message": {"body": "LUL"}}
            ]
            with open(chat_path, "w") as f:
                json.dump(rechat_data, f)
            
            with mock.patch('n8n.trigger') as mock_n8n, \
                 mock.patch('transcript.transcribe_video') as mock_transcribe, \
                 mock.patch('transcript.split_srt_by_hour') as mock_split, \
                 mock.patch('chat_utils.download_chat') as mock_chat:
                
                # Mock sys.argv to simulate command line call
                with mock.patch.object(sys, 'argv', ["twitch_download.py", "https://www.twitch.tv/videos/123456789", "--root_dir", self.root_dir]):
                    twitch_main()
                
                # Check if segments.json was created
                segments_path = os.path.join(video_dir, "segments.json")
                self.assertTrue(os.path.exists(segments_path), "segments.json should be created by the integrated analyzer")

if __name__ == "__main__":
    unittest.main()
