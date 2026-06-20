import os
import re
import argparse
import subprocess


from transcript import transcribe_video 
from encode_subtitle import encode_subtitle
from thumbnail import generate_thumbnail
import ffmpeg

# ================= 配置區域 =================
INPUT_FILE_NAME = "original.mp4"
# defaults (asmongold)
DEFAULT_CROP_CAM = '557:412:5:668'
DEFAULT_CROP_SCREEN = '739:1080:585:0'
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

def build_record(number, start, end, title, hook="", metadata=""):
    return {
        "number": number,
        "start": start,
        "end": end,
        "title": title,
        "hook": hook,
        "metadata": metadata,
    }

def parse_twitch_crop_records(markdown_data):
    """Parse twitch-crop-records.md sections split by ## record headings."""
    records = []
    current_heading = None
    current_lines = []

    def flush_record():
        if current_heading is None:
            return

        fields = {}
        for line in current_lines:
            match = re.match(r"\s*-\s*([^:]+):\s*(.*)\s*$", line)
            if match:
                key = match.group(1).strip().lower()
                fields[key] = match.group(2).strip()

        start = fields.get("start", "")
        end = fields.get("end", "")
        title = fields.get("title", "")
        if not (start and end and title):
            print(f"警告: 跳過不完整的 twitch crop record: {current_heading}")
            return

        record_metadata = "\n".join([current_heading, *current_lines]).strip()
        records.append(build_record(
            number=current_heading.lstrip("#").strip(),
            start=start,
            end=end,
            title=title,
            hook=fields.get("second-title", ""),
            metadata=record_metadata,
        ))

    for raw_line in markdown_data.replace("\ufeff", "").splitlines():
        if re.match(r"^##\s+\S+", raw_line):
            flush_record()
            current_heading = raw_line.strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(raw_line.rstrip())

    flush_record()
    return records

def parse_record_metadata(metadata):
    fields = {}
    for line in metadata.splitlines():
        match = re.match(r"\s*-\s*([^:]+):\s*(.*)\s*$", line)
        if match:
            fields[match.group(1).strip().lower()] = match.group(2).strip()
    return fields

def load_metadata_fields(metadata_path):
    with open(metadata_path, "r", encoding="utf-8") as f:
        return parse_record_metadata(f.read())

def burn_thumbnail_as_first_frame(video_path, thumbnail_path):
    """Replace the first video frame with the generated thumbnail."""
    output_dir = os.path.dirname(os.path.abspath(video_path))
    temp_path = os.path.join(output_dir, ".thumbnail-first-frame.mp4")
    filter_complex = (
        "[1:v]scale=1080:1920[thumbnail];"
        "[0:v][thumbnail]overlay=0:0:enable='eq(n,0)'[video_out]"
    )
    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        thumbnail_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[video_out]",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        temp_path,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg 錯誤: 縮圖寫入第一幀失敗\n{result.stderr}")
            return False

        os.replace(temp_path, video_path)
        return True
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

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

    if start_arg and end_arg:
        print(f"CLI 模式: 剪輯指定區間 {start_arg} - {end_arg}")
        parsed_rows = [build_record(
            number="CLI",
            start=start_arg,
            end=end_arg,
            title=f"Custom_{start_arg}_{end_arg}",
            hook="Manual",
            metadata="\n".join([
                "## CLI",
                "- Title: Manual",
                "- Second-title:",
                f"- Start: {start_arg}",
                f"- End: {end_arg}",
            ]),
        )]
    else:
        # 1. 讀取 twitch-crop-records.md
        twitch_records_path = os.path.join(root_dir, "twitch-crop-records.md")
        if not os.path.exists(twitch_records_path):
            print(f"錯誤: 找不到 twitch-crop-records.md 在 {root_dir}")
            return
        
        print(f"正在讀取: {twitch_records_path}")
        with open(twitch_records_path, "r", encoding="utf-8") as f:
            markdown_data = f.read()

        parsed_rows = parse_twitch_crop_records(markdown_data)

    if not parsed_rows:
        print("錯誤: 找不到有效的 twitch crop records")
        return

    for record in parsed_rows:
        start_ts = record["start"]
        end_ts = record["end"]
        title_text = record["title"]
        title_folder_name = clean_filename(title_text)
        
        # 3. 建立資料夾
        output_folder = os.path.join(root_dir, title_folder_name)
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"建立目錄: {output_folder}")
        metadata_path = os.path.join(output_folder, "metadata.md")
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(record["metadata"])

        # 4. 執行 ffmpeg 指令
        if os.path.exists(input_video_path):
            # Define output path for audio (needed for transcription)
            path_audio = os.path.join(output_folder, "audio.wav")

            print(f"正在剪輯: {title_folder_name} ({start_ts} - {end_ts})...")
            
            success = ffmpeg.crop(
                input_video_path, 
                start_ts,
                end_ts,
                output_folder=output_folder, 
                crop_cam=crop_cam, 
                crop_screen=crop_screen
            )
            
            if not success:
                print(f"FFmpeg 錯誤: 剪輯失敗")
            else:
                # Transcribe audio.mp4
                print("正在產生字幕...")
                subtitle_ready = False
                try:
                    transcribe_video(
                        input_file=path_audio,
                        output_file=os.path.join(output_folder, "transcript.srt"),
                        # speaker_labels=True,
                        # google_translate=True
                    )
                    subtitle_ready = True
                except SystemExit as e:
                    print(f"字幕產生失敗: transcribe_video exited with code {e.code}")
                except Exception as e:
                    print(f"字幕產生失敗: {e}")

                encoded_ready = False
                if subtitle_ready:
                    print("正在壓製字幕...")
                    try:
                        encode_subtitle(
                            os.path.join(output_folder, "stacked.mp4"),
                            os.path.join(output_folder, "result-zh.srt"),
                            os.path.join(output_folder, "result.mp4"),
                        )
                        encoded_ready = True
                    except Exception as e:
                        print(f"字幕壓製失敗: {e}")

                if encoded_ready:
                    print("正在產生縮圖...")
                    thumbnail_ready = False
                    thumbnail_path = os.path.join(output_folder, "thumbnail.jpg")
                    try:
                        fields = load_metadata_fields(metadata_path)
                        generate_thumbnail(
                            os.path.join(output_folder, "stacked.mp4"),
                            fields.get("title") or title_text,
                            output_path=thumbnail_path,
                            second_title=fields.get("second-title") or None,
                            emoji=fields.get("emoji") or None,
                        )
                        thumbnail_ready = True
                    except Exception as e:
                        print(f"縮圖產生失敗: {e}")

                    if thumbnail_ready:
                        print("正在將縮圖寫入影片第一幀...")
                        burn_thumbnail_as_first_frame(
                            os.path.join(output_folder, "result.mp4"),
                            thumbnail_path,
                        )
        else:
            print(f"跳過剪輯 (找不到原始影片): {title_folder_name}")

def main():
    parser = argparse.ArgumentParser(description="自動剪輯工具")
    parser.add_argument("root_dir", help="包含 twitch-crop-records.md 和 original.mp4 的根目錄路徑")
    parser.add_argument("--cam", default=DEFAULT_CROP_CAM, help=f"Camera crop parameter (default: {DEFAULT_CROP_CAM})")
    parser.add_argument("--screen", default=DEFAULT_CROP_SCREEN, help=f"Screen crop parameter (default: {DEFAULT_CROP_SCREEN})")
    parser.add_argument("--start", help="Start time (e.g. 00:00:10). usage with --end")
    parser.add_argument("--end", help="End time (e.g. 00:00:20). usage with --start")
    
    args = parser.parse_args()

    if (args.start and not args.end) or (args.end and not args.start):
        print("錯誤: --start 和 --end 必須同時提供")
        return

    process(args.root_dir, args.cam, args.screen, start_arg=args.start, end_arg=args.end)

if __name__ == "__main__":
    main()
