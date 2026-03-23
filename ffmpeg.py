import os
import subprocess
import datetime
import hashlib

# Constants moved from crop.py
WATERMARK_TEXT = "@StreamFlash"
WATERMARK_FILTER = f"drawtext=text='{WATERMARK_TEXT}':fontfile='/System/Library/Fonts/Helvetica.ttc':alpha=0.5:fontcolor=white:fontsize=36:x=(w-tw)/2:y=(h-th)/2"
STACKED_WATERMARK_FILTER = f"drawtext=text='{WATERMARK_TEXT}':fontfile='/System/Library/Fonts/Helvetica.ttc':alpha=0.5:fontcolor=white:fontsize=40:x=(w-tw)/2:y=(h-th)/4"

def crop(input_video_path, start, end, output_folder=None, crop_cam="260:180:0:298", crop_screen="323:442:249:26"):
    """
    Crops/Cuts the video.
    
    Args:
        input_video_path: Path to input video.
        start: Start time string (e.g. "00:00:10").
        end: End time string.
        output_folder: Destination folder for outputs. If None, generated.
        crop_cam: FFMPEG crop filter string for camera.
        crop_screen: FFMPEG crop filter string for screen.
    """
    
    if not os.path.exists(input_video_path):
        print(f"Error: Input video not found: {input_video_path}")
        return False

    if output_folder is None:
        # Generate name {date}-{HASH} inside input_video_path directory
        parent_dir = os.path.dirname(os.path.abspath(input_video_path))
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        
        # Generate hash based on Start/End to be semi-deterministic or just random?
        # User said "{date}-{HASH}".
        hash_input = f"{input_video_path}{start}{end}{datetime.datetime.now().isoformat()}"
        hash_str = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        folder_name = f"{date_str}-{hash_str}"
        output_folder = os.path.join(parent_dir, folder_name)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output directory: {output_folder}")

    # Define output paths
    path_stacked = os.path.join(output_folder, "stacked.mp4")
    path_cam = os.path.join(output_folder, "cam.mp4")
    path_screen = os.path.join(output_folder, "screen.mp4")
    path_raw = os.path.join(output_folder, "raw.mp4")
    path_audio = os.path.join(output_folder, "audio.wav")

    filter_complex = (
        f"[0:v]crop={crop_cam},scale=1080:640,split=2[cam_base][cam_stack]; "
        f"[0:v]crop={crop_screen},scale=1080:1280,split=2[screen_base][screen_stack]; "
        f"[cam_stack][screen_stack]vstack=inputs=2[stacked_base]; "
        f"[stacked_base]{STACKED_WATERMARK_FILTER}[stacked_out]; "
        f"[cam_base]{WATERMARK_FILTER}[cam_out]; "
        f"[screen_base]{WATERMARK_FILTER}[screen_out]; "
        f"[0:v]{WATERMARK_FILTER}[raw_out]"
    )

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-ss", start, "-to", end, "-i", input_video_path,
        "-map_metadata", "0",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        "-filter_complex", filter_complex,
        
        # Output 1: Stacked
        "-map", "[stacked_out]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast", "-aspect", "9:16",
        path_stacked,
        
        # Output 2: Cam
        "-map", "[cam_out]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
        path_cam,
        
        # Output 3: Screen
        "-map", "[screen_out]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
        path_screen,
        
        # Output 4: Raw
        "-map", "[raw_out]", "-map", "0:a",
        "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
        path_raw,
        
        # Output 5: Audio
        "-map", "0:a", "-vn", path_audio
    ]
    
    # print(f"Executing FFmpeg...")
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg Error:\n{result.stderr}")
        return False
        
    return True
