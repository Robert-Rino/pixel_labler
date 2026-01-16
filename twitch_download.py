import os
import sys
import argparse
import re
import subprocess
import shutil
import json
import transcript
import n8n
import yt_dlp
import datetime

def clean_filename(text):
    """Remove invalid characters for folder names"""
    if not text: return "Untitled"
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def download_video(url, root_dir=".", audio=True):
    print(f"Processing Twitch URL: {url}")
    
    # 1. Fetch Metadata via yt-dlp
    ydl_opts_meta = {
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        sys.exit(1)

    # Construct Title: Twitch_VOD_{creator}_{createdAt}
    # yt-dlp timestamp is usually epoch, upload_date is YYYYMMDD
    uploader = info.get('uploader', 'Unknown')
    upload_date = info.get('upload_date', '00000000') # YYYYMMDD
    timestamp = info.get('timestamp')
    
    # Try to format timestamp nicely if available to match previous createdAt style?
    # twitch-dl createdAt: 2023-10-27T...
    # Let's just use upload_date for simplicity and robustness or format timestamp
    if timestamp:
        dt = datetime.datetime.fromtimestamp(timestamp)
        date_str = dt.strftime("%Y-%m-%dT%H_%M_%S")
    else:
        date_str = upload_date

    title = f'Twitch_VOD_{uploader}_{date_str}'
    original_title = info.get('title', '')
    description = info.get("description", "No description available.")
    duration = info.get("duration", 0)

    print(f"Found Title: {title}")
    # print(f"Original Stream Title: {original_title}")
    print(f"Duration: {duration}s")
    
    safe_title = clean_filename(title)
    safe_title = safe_title[:240] 

    root_dir = os.path.abspath(root_dir)
    output_dir = os.path.join(root_dir, safe_title)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    else:
        print(f"Using existing directory: {output_dir}")

    # 2. Download via yt-dlp
    output_original = os.path.join(output_dir, "original.ts")
    output_audio = os.path.join(output_dir, "audio.mp4")
    srt_output = os.path.join(output_dir, "transcript.srt")

    # 2.1 Video Download (480p)
    print(f"Downloading video '{title}' (480p) via yt-dlp...")
    ydl_opts_video = {
        # # 1. Authentication (Identity)
        # 'cookiefile': 'cookies.txt',  # --cookies cookies.txt

        # 2. Format Selection (Resolution limit)
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',

        # 3. Output Filename Template
        'outtmpl': output_original,

        # 4. Speed & Downloader Settings
        'concurrent_fragment_downloads': 16,  # --concurrent-fragments 16
        
        # This is the Python equivalent of --downloader "m3u8:native"
        # It forces the native downloader for HLS lists to ensure multi-threading works
        'external_downloader': {
            'm3u8': 'native' 
        },

        # 5. Optional: Error Handling
        'retries': 10,
        'fragment_retries': 10,
        'ignoreerrors': True, # Skip if something breaks slightly
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"Video download failed: {e}")
        sys.exit(1)

    if not os.path.exists(output_original):
        print("Error: Video download finished but output file missing.")
        sys.exit(1)

    # 2.2 Audio Download (Direct Audio_Only)
    if audio:
        # Extract Audio from Video using ffmpeg
        ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", output_original,
                '-vn', 
                '-acodec', 'copy',
                output_audio,
            ]
            
        print(f"Extracting audio from: {output_original}...")
        # 使用 subprocess.run 執行並隱藏過多輸出，只顯示錯誤
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg 錯誤:\\n{result.stderr}")
            return

    # 3. Create Metadata File
    metadata_path = os.path.join(output_dir, "metadata.md")
    print(f"Writing metadata to: {metadata_path}")
    
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write("```\n")
        f.write(f"Source: {url}\n")
        f.write(f"Title: {title}\n")
        f.write(f"Original Title: {original_title}\n")
        f.write(f"Description: {description}\n")
        f.write("```\n")

    print(f"Output saved in: {output_dir}")

    # 4. Auto-Transcribe, always do for twitch/twitter flow
    print("Starting transcription...")
    try:
        transcript.transcribe_video(
            input_file=output_audio,
            output_file=srt_output,
        )
    except Exception as e:
        print(f"Transcription failed: {str(e)}")

    transcript.split_srt_by_hour(srt_output)

    # 5. N8N Trigger
    try:
        n8n.trigger('analyze', safe_title)
    except Exception as e:
        print(f"N8N Trigger failed: {e}")

    print("\nDone!")

def main():
    parser = argparse.ArgumentParser(description="Twitch Downloader (via yt-dlp)")
    parser.add_argument("url", help="Twitch VOD URL")
    parser.add_argument("--root_dir", default=".", help="Root directory to create video folder in (default: current directory)")
    parser.add_argument("--audio", action='store_true', default=True, help="Extract audio (default: True)")
    args = parser.parse_args()

    download_video(args.url, root_dir=args.root_dir, audio=args.audio)

if __name__ == "__main__":
    main()
