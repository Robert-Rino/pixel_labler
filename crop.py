import os
import subprocess
import re
import argparse
import sys
import sys
from transcript import transcribe_video, translate_srt_zh 
# ================= 配置區域 =================
INPUT_FILE_NAME = "original.mp4"
# defaults
DEFAULT_CROP_CAM = "640:720:1280:0"
DEFAULT_CROP_SCREEN = "1280:720:0:0"
# ===========================================
# ===========================================
WATERMARK_TEXT = "@StreamFlash"
WATERMARK_FILTER = f"drawtext=text='{WATERMARK_TEXT}':fontfile='/System/Library/Fonts/Helvetica.ttc':alpha=0.5:fontcolor=white:fontsize=36:x=(w-tw)/2:y=(h-th)/2"
STACKED_WATERMARK_FILTER = f"drawtext=text='{WATERMARK_TEXT}':fontfile='/System/Library/Fonts/Helvetica.ttc':alpha=0.5:fontcolor=white:fontsize=40:x=(w-tw)/2:y=(h-th)/3"
def clean_filename(text):
    """移除資料夾名稱中不合法的字元以及 Hashtags"""
    # Remove #hashtags
    text = re.sub(r'#\S+', '', text)
    # Remove invalid chars
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def parse_time_to_seconds(time_str):
    """Convert HH:MM:SS or MM:SS to seconds"""
    parts = list(map(float, time_str.split(":")))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return 0.0

def seconds_to_time_str(seconds):
    """Convert seconds to HH:MM:SS"""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"

def process(root_dir, crop_cam, crop_screen):
    root_dir = os.path.abspath(root_dir)
    if not os.path.exists(root_dir):
        print(f"錯誤: 目錄不存在 - {root_dir}")
        return

    # 1. 讀取 crop_info.md 或 crop_info.csv
    md_path = os.path.join(root_dir, "crop_info.md")
    csv_path = os.path.join(root_dir, "crop_info.csv")
    
    input_file_path = None
    
    if os.path.exists(md_path):
        input_file_path = md_path
    elif os.path.exists(csv_path):
        input_file_path = csv_path
    else:
        print(f"錯誤: 找不到 crop_info.md 或 crop_info.csv 在 {root_dir}")
        return

    print(f"正在讀取: {input_file_path}")
    with open(input_file_path, "r", encoding="utf-8") as f:
        markdown_data = f.read()

    # 2. 確認輸入影片
    input_video_path = os.path.join(root_dir, INPUT_FILE_NAME)
    if not os.path.exists(input_video_path):
        print(f"警告: 找不到影片 {input_video_path}")
        # 嘗試尋找其他 mp4? 或者繼續失敗
        # return 

    # 解析 Markdown (跳過表頭)
    lines = markdown_data.strip().split('\n')
    table_lines = []
    
    # Check if format is Markdown Table (has pipes) or CSV (commas)
    has_pipes = any("|" in line for line in lines[:5])
    
    parsed_rows = []
    
    if has_pipes:
        print("偵測到 Markdown 表格格式")
        start_collecting = False
        for line in lines:
            if line.strip().startswith("|") and "---" in line:
                start_collecting = True
                continue
            if start_collecting and line.strip().startswith("|"):
                cols = [c.strip() for c in line.split('|') if c.strip()]
                if len(cols) >= 6:
                    parsed_rows.append(cols)
    else:
        print("偵測到 CSV 格式")
        import csv
        import io
        # Use csv reader
        # Skip header if looks like header
        reader = csv.reader(io.StringIO(markdown_data))
        for i, row in enumerate(reader):
            if i == 0 and "Shorts Number" in row[0]: continue # Skip header
            if not row: continue
            if len(row) >= 6:
                # Clean whitespace
                cleaned_row = [c.strip() for c in row]
                parsed_rows.append(cleaned_row)

    if not parsed_rows:
        print("錯誤: 找不到有效的內容 (表格或 CSV)")
        return

    # Read root metadata if exists
    root_metadata_path = os.path.join(root_dir, "metadata.md")
    root_metadata_content = ""
    if os.path.exists(root_metadata_path):
        with open(root_metadata_path, "r", encoding="utf-8") as f:
            root_metadata_content = f.read()

    for cols in parsed_rows:
        # 編號 | 開始時間 | 結束時間 | 片段摘要 | 賣點建議標題 | Hook建議副標題
        # cols[0] = 編號, cols[1] = Start, cols[2] = End, cols[3] = Summary, cols[4] = Title, cols[5] = Hook
        
        start_ts = cols[1]
        end_ts = cols[2]
        title_folder_name = clean_filename(cols[4])
        hook_text = cols[5]
        
        # 3. 建立資料夾
        output_folder = os.path.join(root_dir, title_folder_name)
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"建立目錄: {output_folder}")

        # 4. 執行 ffmpeg 指令
        if os.path.exists(input_video_path):
            # Calculate padded time
            start_seconds = parse_time_to_seconds(start_ts)
            end_seconds = parse_time_to_seconds(end_ts)
            
            # Start - 5s, End + 5s
            # Clamp start to 0
            adj_start = max(0, start_seconds - 5)
            # End just adds 5s
            adj_end = end_seconds + 5
            
            # Convert back to string for ffmpeg
            adj_start_str = seconds_to_time_str(adj_start)
            adj_end_str = seconds_to_time_str(adj_end)

            # Define output paths
            path_stacked = os.path.join(output_folder, "stacked.mp4")
            path_cam = os.path.join(output_folder, "cam.mp4")
            path_screen = os.path.join(output_folder, "screen.mp4")
            path_raw = os.path.join(output_folder, "raw.mp4")
            path_audio = os.path.join(output_folder, "audio.wav")

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-ss", adj_start_str, "-to", adj_end_str, "-i", input_video_path,
                '-map_metadata', '0',
                '-avoid_negative_ts', 'make_zero',
                '-movflags', '+faststart',
                "-filter_complex", 
                # 1. Crop & Scale & Split
                f"[0:v]crop={crop_cam},scale=1080:640,split=2[cam_base][cam_stack]; "
                f"[0:v]crop={crop_screen},scale=1080:1280,split=2[screen_base][screen_stack]; "
                
                # 2. Stack
                f"[cam_stack][screen_stack]vstack=inputs=2[stacked_base]; "
                
                # 3. Apply Watermark
                f"[stacked_base]{STACKED_WATERMARK_FILTER}[stacked_out]; "
                f"[cam_base]{WATERMARK_FILTER}[cam_out]; "
                f"[screen_base]{WATERMARK_FILTER}[screen_out]; "
                f"[0:v]{WATERMARK_FILTER}[raw_out]",
                
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
                "-map", "0:a",
                "-vn",
                path_audio
            ]
            
            print(f"正在剪輯: {title_folder_name} ({start_ts} - {end_ts})...")
            # 使用 subprocess.run 執行並隱藏過多輸出，只顯示錯誤
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg 錯誤:\\n{result.stderr}")
            else:
                # Transcribe audio.mp4
                print("正在產生字幕...")
                try:
                    transcribe_video(
                        input_file=path_audio,
                        output_file=os.path.join(output_folder, "transcript.srt"),
                        speaker_labels=True,
                    )
                except Exception as e:
                    print(f"字幕產生失敗: {e}")
        else:
            print(f"跳過剪輯 (找不到原始影片): {title_folder_name}")

        # 5. 產生 metadata.md
        clip_metadata = '\n'.join([
            f'{start_ts} -> {end_ts}',
            '# 標題', cols[4],
            '# 副標題', hook_text,
        ])
        
        final_metadata = clip_metadata
        if root_metadata_content:
            final_metadata = f"{root_metadata_content}\n==========\n\n{clip_metadata}"
            
        with open(os.path.join(output_folder, "metadata.md"), "w", encoding="utf-8") as f:
            f.write(final_metadata)

def main():
    parser = argparse.ArgumentParser(description="自動剪輯工具")
    parser.add_argument("root_dir", help="包含 crop_info.md 和 original.mp4 的根目錄路徑")
    parser.add_argument("--cam", default=DEFAULT_CROP_CAM, help=f"Camera crop parameter (default: {DEFAULT_CROP_CAM})")
    parser.add_argument("--screen", default=DEFAULT_CROP_SCREEN, help=f"Screen crop parameter (default: {DEFAULT_CROP_SCREEN})")
    
    args = parser.parse_args()
    process(args.root_dir, args.cam, args.screen)

if __name__ == "__main__":
    main()