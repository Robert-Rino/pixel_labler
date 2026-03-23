import unittest
import numpy as np
import os
import subprocess
import json
from analyzer import extract_audio_peaks, analyze_chat_velocity

class TestAudioAnalyzer(unittest.TestCase):
    def setUp(self):
        # Generate a 10-second test audio file with a peak between 5s and 6s
        # We use a low volume sine wave and a high volume section
        self.test_file = "test_audio_sample.wav"
        if not os.path.exists(self.test_file):
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "sine=f=440:d=10,volume='if(between(t,5,6), 1.0, 0.1)':eval=frame",
                self.test_file
            ]
            subprocess.run(cmd, check=True, capture_output=True)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_extract_audio_peaks(self):
        # We expect a peak around 5s or 6s
        peaks = extract_audio_peaks(self.test_file, threshold_factor=2.0, window_size=1.0)
        
        # Verify peaks is a list
        self.assertIsInstance(peaks, list)
        
        # We expect at least one peak in the 5-6s range
        # Depending on how the window and rolling average are calculated, it should be around there
        found_in_range = any(5.0 <= p[0] <= 7.0 for p in peaks)
        self.assertTrue(found_in_range, f"Expected peak between 5s and 7s, found: {peaks}")
        
        # Verify no peaks in the quiet part (0-4s)
        found_in_quiet = any(0.0 <= p[0] <= 4.0 for p in peaks)
        self.assertFalse(found_in_quiet, f"Found unexpected peaks in quiet section: {peaks}")

class TestChatAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_json = "test_rechat.json"
        
        # Mock rechat data
        # Quiet period: 0-20s (1 message every 5s)
        # Spike: 25-35s (10 messages in 10s, some with emotes)
        # Quiet period: 40-60s (1 message every 5s)
        data = []
        for t in range(0, 21, 5):
            data.append({"content_offset_seconds": float(t), "message": {"body": "hello"}})
            
        # Spike at 30s
        for t in range(25, 36):
            msg = "Pog" if t % 2 == 0 else "wow"
            data.append({"content_offset_seconds": float(t), "message": {"body": msg}})
            
        for t in range(40, 61, 5):
            data.append({"content_offset_seconds": float(t), "message": {"body": "hello"}})
            
        with open(self.test_json, "w") as f:
            json.dump(data, f)

    def tearDown(self):
        if os.path.exists(self.test_json):
            os.remove(self.test_json)

    def test_analyze_chat_velocity(self):
        # window_size=10, threshold_factor=1.5
        spikes = analyze_chat_velocity(self.test_json, window_size=10, threshold_factor=1.5)
        
        # Verify spikes is a list
        self.assertIsInstance(spikes, list)
        
        # We expect a spike around 30s
        # 25-35s has 11 messages. Weighted (5 * 2.0 + 6 * 1.0) = 16.0
        # Quiet periods have 2-3 messages per 10s window. Weighted = 2.0-3.0
        # Baseline should be around 2.0-3.0. 16.0 is way above 1.5 * baseline.
        found_spike = any(25.0 <= s[0] <= 35.0 for s in spikes)
        self.assertTrue(found_spike, f"Expected spike around 30s, found: {spikes}")
        
        # Verify no spikes in quiet periods
        found_in_quiet = any(0.0 <= s[0] <= 20.0 or 45.0 <= s[0] <= 60.0 for s in spikes)
        self.assertFalse(found_in_quiet, f"Found unexpected spikes in quiet section: {spikes}")

class TestSignalFusion(unittest.TestCase):
    def test_find_segments_basic(self):
        from analyzer import find_segments
        # Mock peaks and spikes with scores
        audio_peaks = [(10.0, 2.5), (100.0, 3.0)] # (timestamp, score)
        chat_spikes = [(12.0, 2.0), (200.0, 4.0)]
        
        # 10.0 (audio) and 12.0 (chat) are within 15s -> one event
        # 100.0 (audio) is alone -> one event
        # 200.0 (chat) is alone -> one event
        
        segments = find_segments(audio_peaks, chat_spikes, video_duration=3600)
        
        # Should have 3 segments
        self.assertEqual(len(segments), 3)
        
        # First segment: start 5s before first spike (10.0 - 5 = 5.0), 
        # end 10s after last signal (12.0 + 10 = 22.0)
        # Score: 2.5 + 2.0 = 4.5
        self.assertEqual(segments[0]['start'], "00:00:05")
        self.assertEqual(segments[0]['end'], "00:00:22")
        self.assertAlmostEqual(segments[0]['score'], 4.5)
        self.assertIn("Audio + Chat", segments[0]['reason'])

    def test_find_segments_ranking(self):
        from analyzer import find_segments
        # Create many spikes in the first hour
        audio_peaks = [(float(i * 60), 2.0) for i in range(20)]
        chat_spikes = []
        
        # Should return top 10 for the first hour
        segments = find_segments(audio_peaks, chat_spikes, video_duration=3600)
        self.assertEqual(len(segments), 10)

if __name__ == "__main__":
    unittest.main()
