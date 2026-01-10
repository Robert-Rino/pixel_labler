import os
import sys
import argparse
import re
import yt_dlp
from transcript import transcribe_video

def clean_filename(text):
    """Remove invalid characters for folder names"""
    # Replace invalid chars with underscore or empty
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def validate_youtube_url(url):
    """Simple validation for YouTube URLs"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})|'
        r'(https?://)?(www\.)?youtube\.com/shorts/([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url) is not None

def download_video(url, root_dir=".", force_transcript=False):
    if not validate_youtube_url(url):
        print(f"Error: Invalid YouTube URL: {url}")
        sys.exit(1)

    print(f"Processing URL: {url}")

    # 1. Get Video Information (Metadata)
    ydl_opts_meta = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        sys.exit(1)

    title = info.get('title', 'Untitled')
    description = info.get('description', '')
    
    safe_title = clean_filename(title)
    safe_title = safe_title[:240] 

    root_dir = os.path.abspath(root_dir)
    output_dir = os.path.join(root_dir, safe_title)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    else:
        print(f"Using existing directory: {output_dir}")

    # 2. Download Video
    output_template = os.path.join(output_dir, "original.mp4")
    
    ydl_opts_download = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
    }

    print(f"Downloading video '{title}'...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)

    # 3. Create Metadata File
    metadata_path = os.path.join(output_dir, "metadata.md")
    print(f"Writing metadata to: {metadata_path}")
    
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write("```\n")
        f.write(f"Source: {url}\n")
        f.write(f"Title: {title}\n")
        f.write(f"Description: {description}\n")
        f.write("```\n")

    print(f"Output saved in: {output_dir}")

    # 4. Auto-Transcribe if Short
    is_short = "/shorts/" in url or (duration > 0 and duration < 180)
    
    
    if is_short or force_transcript:
        reason = "Short video" if is_short else "Forced via flag"
        print(f"\n[Auto-Transcribe] Triggered ({reason}).")
        print("Starting transcription...")
        try:
            transcribe_video(
                input_file=output_template,
                output_file="zh.srt", # transcript.py logic will put this in same dir as input if simple filename
                translate_to_zh=True
            )
        except Exception as e:
            print(f"Transcription failed: {str(e)}")
    else:
        print(f"\nVideo duration is {duration}s. Skipping auto-transcription (only for < 180s).")

    print("\nDone!")

def main():
    parser = argparse.ArgumentParser(description="YouTube Downloader")
    parser.add_argument("url", help="YouTube Video URL")
    parser.add_argument("--root_dir", default=".", help="Root directory to create video folder in (default: current directory)")
    parser.add_argument("--transcript", action="store_true", default=False, help="Force generate transcript")
    args = parser.parse_args()

    download_video(args.url, root_dir=args.root_dir, force_transcript=args.transcript)

if __name__ == "__main__":
    main()
