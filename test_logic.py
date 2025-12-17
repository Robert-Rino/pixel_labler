import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock tkinter before importing anything that uses it
sys.modules['tkinter'] = MagicMock()
sys.modules['tkinter.filedialog'] = MagicMock()
sys.modules['tkinter.ttk'] = MagicMock()

import tkinter as tk
# Now we can import main
from main import FFmpegCropTool

class TestFFmpegCropTool(unittest.TestCase):
    def setUp(self):
        self.mock_root = MagicMock()
        self.app = FFmpegCropTool(self.mock_root)
        
        # Mock the image dimensions
        self.app.original_image = MagicMock()
        self.app.original_image.shape = (1080, 1920, 3) # h, w, c
    
    def test_coordinate_conversion(self):
        # Simulate a state where image is scaled to 50%
        self.app.scale_factor = 0.5
        self.app.img_offset_x = 100
        self.app.img_offset_y = 50
        
        # Test 1: Top-Left of image displayed on canvas
        # Canvas: 100, 50 -> Image: 0, 0
        ix, iy = self.app.canvas_to_image_coords(100, 50)
        self.assertEqual((ix, iy), (0, 0))
        
        # Test 2: Point (200, 200) on Image
        # Canvas = 200 * 0.5 + 100 = 200
        # Canvas = 200 * 0.5 + 50 = 150
        ix, iy = self.app.canvas_to_image_coords(200, 150)
        self.assertEqual((ix, iy), (200, 200))
        
    def test_ffmpeg_string_generation(self):
        # Add a rectangle: x=10, y=20, w=100, h=50
        self.app.rectangles = [(10, 20, 100, 50)]
        
        # Mock the Text widget
        self.app.output_text = MagicMock()
        
        self.app.update_output()
        
        # Verify calls to insert
        expected_str = "crop=100:50:10:20\n"
        self.app.output_text.insert.assert_called_with(tk.END, expected_str)

    def test_time_parsing(self):
        # Mock Frame Entry
        self.app.frame_entry = MagicMock()
        
        # Mock VideoCapture for FPS
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0 # 30 FPS
        self.app.cap = mock_cap
        
        # Mock load_video to do nothing
        self.app.load_video = MagicMock()

        # Test Case 1: Seconds "2s" -> 2 * 30 + 1 = 61
        self.app.frame_entry.get.return_value = "2s"
        self.app.reload_frame()
        self.assertEqual(self.app.frame_num, 61)

        # Test Case 2: Time "00:01:00" -> 60 * 30 + 1 = 1801
        self.app.frame_entry.get.return_value = "00:01:00"
        self.app.reload_frame()
        self.assertEqual(self.app.frame_num, 1801)
        
        # Test Case 3: MM:SS "1:30" -> 90 * 30 + 1 = 2701
        self.app.frame_entry.get.return_value = "1:30"
        self.app.reload_frame()
        self.assertEqual(self.app.frame_num, 2701)

        # Test Case 4: Normal Frame "100"
        self.app.frame_entry.get.return_value = "100"
        self.app.reload_frame()
        self.assertEqual(self.app.frame_num, 100)

if __name__ == '__main__':
    unittest.main()
