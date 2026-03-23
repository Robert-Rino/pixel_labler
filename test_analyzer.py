import unittest
import numpy as np
import os
import subprocess
from analyzer import extract_audio_peaks

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
        found_in_range = any(5.0 <= p <= 7.0 for p in peaks)
        self.assertTrue(found_in_range, f"Expected peak between 5s and 7s, found: {peaks}")
        
        # Verify no peaks in the quiet part (0-4s)
        found_in_quiet = any(0.0 <= p <= 4.0 for p in peaks)
        self.assertFalse(found_in_quiet, f"Found unexpected peaks in quiet section: {peaks}")

if __name__ == "__main__":
    unittest.main()
