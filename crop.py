import os
import re
import argparse
from transcript import transcribe_video 
import ffmpeg
from facecam_utils import detect_facecam

# ================= 配置區域 =================
INPUT_FILE_NAME = "original.mp4"
# defaults
DEFAULT_CROP_CAM = "260:180:0:298"
DEFAULT_CROP_SCREEN = "323:442:249:26"
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

def process(root_dir, crop_cam, crop_screen, start_arg=None, end_arg=None):
    root_dir = os.path.abspath(root_dir)
    if not os.path.exists(root_dir):
        print(f"錯誤: 目錄不存在 - {root_dir}")
        return

    # 2. 確認輸入影片 (Check early for single chunk mode)
    input_video_path = os.path.join(root_dir, INPUT_FILE_NAME)
    if not os.path.exists(input_video_path):
        print(f"警告: 找不到影片 {input_video_path}")
        return 

    parsed_rows = []

    # Check for CLI Override
    if start_arg and end_arg:
        print(f"CLI 模式: 剪輯指定區間 {start_arg} - {end_arg}")
        # Fake row: No Number, Start, End, Summary, Title='Custom_Clip', Hook='CLI'
        # cols structure: [No, Start, End, Summary, Title, Hook]
        parsed_rows.append(["CLI", start_arg, end_arg, "CLI Manual Clip", f"Custom_{start_arg}_{end_arg}", "Manual"])
    else:
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

        # 解析 Markdown (跳過表頭)
        lines = markdown_data.strip().split('\n')
        
        # Check if format is Markdown Table (has pipes) or CSV (commas)
        has_pipes = any("|" in line for line in lines[:5])
        
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
            reader = csv.reader(io.StringIO(markdown_data))
            for i, row in enumerate(reader):
                if i == 0 and "Shorts Number" in row[0]: continue # Skip header
                if not row: continue
                if len(row) >= 6:
                    cleaned_row = [c.strip() for c in row]
                    parsed_rows.append(cleaned_row)

    if not parsed_rows:
        print("錯誤: 找不到有效的內容 (表格或 CSV 或 CLIArgs)")
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

            # Define output path for audio (needed for transcription)
            path_audio = os.path.join(output_folder, "audio.wav")

            print(f"正在剪輯: {title_folder_name} ({start_ts} - {end_ts})...")
            
            success = ffmpeg.crop(
                input_video_path, 
                adj_start_str, 
                adj_end_str, 
                output_folder=output_folder, 
                crop_cam=crop_cam, 
                crop_screen=crop_screen
            )
            
            if not success:
                print(f"FFmpeg 錯誤: 剪輯失敗")
            else:
                # Transcribe audio.mp4
                print("正在產生字幕...")
                try:
                    transcribe_video(
                        input_file=path_audio,
                        output_file=os.path.join(output_folder, "transcript.srt"),
                        # speaker_labels=True,
                        # google_translate=True
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

def resolve_cam_param(root_dir, cam_arg):
    if cam_arg != "auto":
        return cam_arg
        
    input_video_path = os.path.join(root_dir, INPUT_FILE_NAME)
    if not os.path.exists(input_video_path):
        print(f"Warning: {input_video_path} not found. Using default: {DEFAULT_CROP_CAM}")
        return DEFAULT_CROP_CAM

    print("Auto-detecting facecam (ML)...")
    detected = detect_facecam(input_video_path)
    if detected:
        print(f"Detected: {detected}")
        return detected
    
    print(f"Detection failed. Using default: {DEFAULT_CROP_CAM}")
    return DEFAULT_CROP_CAM

def main():
    parser = argparse.ArgumentParser(description="自動剪輯工具")
    parser.add_argument("root_dir", help="包含 crop_info.md 和 original.mp4 的根目錄路徑")
    parser.add_argument("--cam", default=DEFAULT_CROP_CAM, help=f"Camera crop parameter (default: {DEFAULT_CROP_CAM}). Use 'auto' for ML detection.")
    parser.add_argument("--screen", default=DEFAULT_CROP_SCREEN, help=f"Screen crop parameter (default: {DEFAULT_CROP_SCREEN})")
    parser.add_argument("--start", help="Start time (e.g. 00:00:10). usage with --end")
    parser.add_argument("--end", help="End time (e.g. 00:00:20). usage with --start")
    
    args = parser.parse_args()

    if (args.start and not args.end) or (args.end and not args.start):
        print("錯誤: --start 和 --end 必須同時提供")
        return

    cam_param = resolve_cam_param(args.root_dir, args.cam)
    process(args.root_dir, cam_param, args.screen, start_arg=args.start, end_arg=args.end)

if __name__ == "__main__":
    main()