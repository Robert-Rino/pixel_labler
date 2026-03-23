import unittest
import os
import json
import shutil
import subprocess
from twitch_download import download_video

class TestE2EMocked(unittest.TestCase):
    def setUp(self):
        self.root_dir = "test_e2e_output"
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir)
            
        # We need to simulate the folder structure twitch_download creates
        # Title format: Twitch_VOD_{uploader}_{date_str}
        # For simplicity, we'll mock the metadata part or just use a known folder name
        # But download_video fetches metadata via yt-dlp, which might fail if URL is invalid.
        # Let's mock yt_dlp or use a real but short URL if possible.
        # Actually, let's just mock the folder it would create.
        
        # To avoid yt-dlp metadata fetch, we might need to mock it.
        # But wait, download_video calls yt-dlp first thing.

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
            
            # We want to catch the moment after the directory is created but before yt-dlp download starts.
            # However, download_video is one big function.
            # Alternative: Since we know the title it will generate, we can just match it.
            # Based on previous run, it was Twitch_VOD_testuser_2023-01-01T08_00_00
            
            # Let's mock download_video's internal yt-dlp call to actually create the file
            # or just mock os.path.exists for original.mp4 to return True.
            
            # Actually, the simplest way is to mock yt-dlp download to just create a dummy file.
            def mock_download(urls):
                # The output path is in ydl_opts_video['outtmpl']
                # But we don't have easy access to it here.
                pass

            # Let's try to mock os.path.exists specifically for the check it does.
            original_exists = [False] # First check: False (to enter download), then we want it to be True?
            # No, if it's False, it tries to download.
            
            # Let's just mock the folder it would create, but use a glob to find it.
            # Or better, let's use a side_effect on a mock that we know is called after directory creation.
            
            # I will just use the exact name from the previous error for now, 
            # but I'll make it more flexible.
            
            date_str = "2023-01-01T08_00_00" # Based on previous failure
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
                 mock.patch('transcript.split_srt_by_hour') as mock_split:
                
                download_video("https://www.twitch.tv/videos/123456789", root_dir=self.root_dir, audio=True)
                
                # Check if segments.json was created
                segments_path = os.path.join(video_dir, "segments.json")
                self.assertTrue(os.path.exists(segments_path), "segments.json should be created by the integrated analyzer")

if __name__ == "__main__":
    unittest.main()
