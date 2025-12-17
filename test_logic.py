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

if __name__ == '__main__':
    unittest.main()
