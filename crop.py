import os
import subprocess
import re
import argparse
import sys

# ================= 配置區域 =================
INPUT_FILE_NAME = "original.mp4"
# defaults
DEFAULT_CROP_CAM = "640:720:1280:0"
DEFAULT_CROP_SCREEN = "1280:720:0:0"
# ===========================================

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

    # 1. 讀取 crop_info.md
    md_path = os.path.join(root_dir, "crop_info.md")
    if not os.path.exists(md_path):
        print(f"錯誤: 找不到 {md_path}")
        return

    print(f"正在讀取: {md_path}")
    with open(md_path, "r", encoding="utf-8") as f:
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
            if i == 0 and "編號" in row[0]: continue # Skip header
            if not row: continue
            if len(row) >= 6:
                # Clean whitespace
                cleaned_row = [c.strip() for c in row]
                parsed_rows.append(cleaned_row)

    if not parsed_rows:
        print("錯誤: 找不到有效的內容 (表格或 CSV)")
        return

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

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-ss", adj_start_str, "-to", adj_end_str, "-i", input_video_path,
                "-filter_complex", 
                f"[0:v]crop={crop_cam},scale=1080:960,split=2[cam_out][cam_stack]; "
                f"[0:v]crop={crop_screen},scale=1080:960,split=2[screen_out][screen_stack]; "
                f"[screen_stack][cam_stack]vstack=inputs=2[stacked_out]",
                
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
                "-map", "0:v", "-map", "0:a",
                "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                path_raw
            ]
            
            print(f"正在剪輯: {title_folder_name} ({start_ts} - {end_ts})...")
            # 使用 subprocess.run 執行並隱藏過多輸出，只顯示錯誤
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"FFmpeg 錯誤:\n{result.stderr}")
        else:
            print(f"跳過剪輯 (找不到原始影片): {title_folder_name}")

        # 5. 產生 metadata.md
        metadata_content = f"# 標題\n{cols[4]}\n\n# 副標題\n{hook_text}"
        with open(os.path.join(output_folder, "metadata.md"), "w", encoding="utf-8") as f:
            f.write(metadata_content)

def main():
    parser = argparse.ArgumentParser(description="自動剪輯工具")
    parser.add_argument("root_dir", help="包含 crop_info.md 和 original.mp4 的根目錄路徑")
    parser.add_argument("--cam", default=DEFAULT_CROP_CAM, help=f"Camera crop parameter (default: {DEFAULT_CROP_CAM})")
    parser.add_argument("--screen", default=DEFAULT_CROP_SCREEN, help=f"Screen crop parameter (default: {DEFAULT_CROP_SCREEN})")
    
    args = parser.parse_args()
    process(args.root_dir, args.cam, args.screen)

if __name__ == "__main__":
    main()