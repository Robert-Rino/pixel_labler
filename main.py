import tkinter as tk
from tkinter import filedialog, ttk
import cv2
from PIL import Image, ImageTk
import argparse
import sys
import os

class FFmpegCropTool:
    def __init__(self, root, video_path=None, frame_num=1):
        self.root = root
        self.root.title("FFmpeg Crop Tool")
        
        self.video_path = video_path
        self.frame_num = frame_num
        self.cap = None
        self.original_image = None
        self.display_image = None
        self.photo = None
        self.scale_factor = 1.0
        
        self.rectangles = []  # List of (rect_id, x1, y1, x2, y2)
        self.start_x = None
        self.start_y = None
        self.current_rect = None
        
        # UI Setup
        self.setup_ui()
        
        # Load video if provided
        if self.video_path:
            self.load_video()
        else:
            # Delay opening file dialog slightly to let mainloop start or show UI first
            self.root.after(100, self.open_file_dialog)

    def setup_ui(self):
        # Control Panel (Left/Top)
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(control_frame, text="Open Video", command=self.open_file_dialog).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(control_frame, text="Frame/Time:").pack(side=tk.LEFT, padx=5)
        self.frame_entry = ttk.Entry(control_frame, width=10)
        self.frame_entry.insert(0, str(self.frame_num))
        self.frame_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Go", command=self.reload_frame).pack(side=tk.LEFT)
        
        ttk.Button(control_frame, text="Reset Crops", command=self.reset_crops).pack(side=tk.LEFT, padx=20)
        
        self.coord_label = ttk.Label(control_frame, text="Mouse: (0, 0)")
        self.coord_label.pack(side=tk.RIGHT, padx=10)

        # Canvas for Image
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="black", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.update_mouse_coords)
        self.canvas.bind("<Configure>", self.on_resize)

        # Output Panel (Bottom)
        output_frame = ttk.LabelFrame(self.root, text="FFmpeg Crop Parameters", padding="10")
        output_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.output_text = tk.Text(output_frame, height=5)
        self.output_text.pack(fill=tk.X)

    def open_file_dialog(self):
        filename = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv")])
        if filename:
            self.video_path = filename
            self.load_video()

    def reload_frame(self):
        input_str = self.frame_entry.get().strip()
        
        # Need FPS to convert time -> frame
        # We ensure cap is available or open it temporarily
        temp_cap = None
        current_fps = 30.0
        
        if self.cap is not None and self.cap.isOpened():
            current_fps = self.cap.get(cv2.CAP_PROP_FPS)
        elif self.video_path:
            try:
                temp_cap = cv2.VideoCapture(self.video_path)
                if temp_cap.isOpened():
                    current_fps = temp_cap.get(cv2.CAP_PROP_FPS)
            finally:
                if temp_cap: temp_cap.release()
        
        if current_fps <= 0: current_fps = 30.0

        try:
            target_frame = self.frame_num
            
            if ":" in input_str:
                # HH:MM:SS or MM:SS
                parts = list(map(float, input_str.split(":")))
                seconds = 0
                if len(parts) == 3: # HH:MM:SS
                    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2: # MM:SS
                    seconds = parts[0] * 60 + parts[1]
                else: 
                     # Just assume seconds if weird format like "30" but with logic flow this hits number check usually
                     pass
                target_frame = int(seconds * current_fps) + 1
                
            elif input_str.lower().endswith("s"):
                seconds = float(input_str[:-1])
                target_frame = int(seconds * current_fps) + 1
                
            else:
                target_frame = int(input_str)

            self.frame_num = target_frame
            
        except ValueError:
            pass # Keep old value
            
        self.load_video()

    def load_video(self):
        if not self.video_path:
            return
            
        if self.cap is not None:
            self.cap.release()
            
        self.cap = cv2.VideoCapture(self.video_path)
        
        if not self.cap.isOpened():
            print(f"Error: Could not open video {self.video_path}")
            return
            
        # Set frame position (0-based index, so frame_num - 1)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, self.frame_num - 1))
        ret, frame = self.cap.read()
        
        if ret:
            # Convert BGR to RGB
            self.original_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.display_image_on_canvas()
        else:
            print(f"Error: Could not read frame {self.frame_num}")
            
    def display_image_on_canvas(self):
        if self.original_image is None:
            return
            
        # Get canvas dimensions (or window dimensions if canvas not ready)
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            # If canvas hasn't been drawn yet, use a default or wait
            canvas_width = 800
            canvas_height = 600

        img_h, img_w, _ = self.original_image.shape
        
        # Calculate scale to fit
        scale_w = canvas_width / img_w
        scale_h = canvas_height / img_h
        self.scale_factor = min(scale_w, scale_h, 1.0) # Do not upscale
        
        new_w = int(img_w * self.scale_factor)
        new_h = int(img_h * self.scale_factor)
        
        resized_image = cv2.resize(self.original_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        self.display_image = Image.fromarray(resized_image)
        self.photo = ImageTk.PhotoImage(image=self.display_image)
        
        self.canvas.delete("all")
        # Center image
        x_centered = (canvas_width - new_w) // 2
        y_centered = (canvas_height - new_h) // 2
        
        self.canvas.create_image(x_centered, y_centered, anchor=tk.NW, image=self.photo, tags="image")
        
        # Store offset for coordinate checking
        self.img_offset_x = x_centered
        self.img_offset_y = y_centered
        
        # Redraw existing rectangles
        self.redraw_rectangles()

    def on_resize(self, event):
        if self.original_image is not None:
            # Debounce or just redraw? simple redraw might be laggy for large videos but ok for MVP
            self.display_image_on_canvas()

    def canvas_to_image_coords(self, cx, cy):
        if self.scale_factor == 0: return 0, 0
        ix = int((cx - self.img_offset_x) / self.scale_factor)
        iy = int((cy - self.img_offset_y) / self.scale_factor)
        
        # Clamp to image bounds
        img_h, img_w, _ = self.original_image.shape
        ix = max(0, min(ix, img_w))
        iy = max(0, min(iy, img_h))
        
        return ix, iy

    def update_mouse_coords(self, event):
        if self.original_image is not None:
            ix, iy = self.canvas_to_image_coords(event.x, event.y)
            self.coord_label.config(text=f"Mouse: ({ix}, {iy})")

    def on_mouse_down(self, event):
        if self.original_image is None: return
        self.start_x = event.x
        self.start_y = event.y
        self.current_rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2)

    def on_mouse_drag(self, event):
        if self.current_rect:
            self.canvas.coords(self.current_rect, self.start_x, self.start_y, event.x, event.y)
            self.update_mouse_coords(event)

    def on_mouse_up(self, event):
        if self.current_rect:
            # Normalize coordinates (handle dragging left/up)
            x1, y1, x2, y2 = self.canvas.coords(self.current_rect)
            # Store in normalized form
            real_x1 = min(x1, x2)
            real_y1 = min(y1, y2)
            real_x2 = max(x1, x2)
            real_y2 = max(y1, y2)

            self.rectangles.append((real_x1, real_y1, real_x2, real_y2))
            
            # Remove the temporary dragging rect and redraw properly managed rects (optional, but cleaner if we resize)
            self.canvas.delete(self.current_rect)
            self.redraw_rectangles()
            self.update_output()
            self.current_rect = None

    def redraw_rectangles(self):
        # Clear only rectangle objects? Easier to verify "image" tag vs others
        # For this simple version, we might just clear all and redraw image + rects
        # But we already cleared all in display_image_on_canvas
        
        # We need to know which canvas objects are rectangles. 
        # A simpler approach: Store rectangles in Image Coordinates, then draw them on canvas
        # The current implementation stored canvas coords in `self.rectangles` which is wrong if we resize!
        # FIXED LOGIC:
        pass # See fix below in stored logic

    # Redefine logic for storing rectangles:
    # We should store Image Coordinates in self.rectangles
    
    def on_mouse_up_fixed(self, event):
        # ... logic to store image coords
        pass
        
    # Let's fix the class methods now to correct the storage issue
    
    def on_mouse_up(self, event):
        if self.current_rect:
            c_x1, c_y1, c_x2, c_y2 = self.canvas.coords(self.current_rect)
            self.canvas.delete(self.current_rect)
            self.current_rect = None
            
            # Convert to image coords
            ix1, iy1 = self.canvas_to_image_coords(c_x1, c_y1)
            ix2, iy2 = self.canvas_to_image_coords(c_x2, c_y2)
            
            # Normalize
            x = min(ix1, ix2)
            y = min(iy1, iy2)
            w = abs(ix1 - ix2)
            h = abs(iy1 - iy2)
            
            if w > 0 and h > 0:
                self.rectangles.append((x, y, w, h))
                self.redraw_rectangles()
                self.update_output()

    def redraw_rectangles(self):
        # Ensure image is drawn first (handled by display_image_on_canvas)
        # But wait, display_image_on_canvas clears everything. 
        # So we should call Draw Rects inside Display Image OR call Display Image then Draw Rects.
        # display_image_on_canvas calls this at the end.
        
        # Remove old rects? 
        # We can tag them.
        self.canvas.delete("rect")
        
        for (x, y, w, h) in self.rectangles:
            # Convert back to canvas coords
            cx1 = x * self.scale_factor + self.img_offset_x
            cy1 = y * self.scale_factor + self.img_offset_y
            cx2 = (x + w) * self.scale_factor + self.img_offset_x
            cy2 = (y + h) * self.scale_factor + self.img_offset_y
            
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="red", width=2, tags="rect")
            # Label
            self.canvas.create_text(cx1, cy1 - 10, text=f"{w}x{h}", fill="red", anchor=tk.SW, tags="rect")

    def update_output(self):
        self.output_text.delete("1.0", tk.END)
        for (x, y, w, h) in self.rectangles:
            line = f"crop={w}:{h}:{x}:{y}\n"
            self.output_text.insert(tk.END, line)

    def reset_crops(self):
        self.rectangles = []
        self.output_text.delete("1.0", tk.END)
        self.redraw_rectangles()

def main():
    parser = argparse.ArgumentParser(description="FFmpeg Crop Tool")
    parser.add_argument("--video_path", type=str, help="Path to video file")
    parser.add_argument("--frame", type=int, default=1, help="Frame number to extract (1-based)")
    
    args = parser.parse_args()
    
    root = tk.Tk()
    root.geometry("1000x800")
    
    app = FFmpegCropTool(root, video_path=args.video_path, frame_num=args.frame)
    
    root.mainloop()

if __name__ == "__main__":
    main()
