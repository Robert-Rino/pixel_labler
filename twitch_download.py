import os
import sys
import argparse
import re
import subprocess
import shutil
import json
from transcript import transcribe_video

def clean_filename(text):
    """Remove invalid characters for folder names"""
    if not text: return "Untitled"
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def validate_twitch_url(url):
    """Simple validation for Twitch VOD URLs"""
    twitch_regex = (
        r'(https?://)?(www\.)?'
        r'(twitch\.tv|twitch\.com)/'
        r'(videos|video|v)/'
        r'(\d+)'
    )
    return re.match(twitch_regex, url) is not None

def get_twitch_info(url):
    """
    Use 'twitch-dl info <url> --json' to fetch metadata.
    Returns parsed dict or None.
    """
    cmd = ["twitch-dl", "info", url, "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching metadata with twitch-dl: {e.stderr}")
        return None
    except json.JSONDecodeError:
        print("Error parsing twitch-dl output JSON.")
        return None

def download_video(url, root_dir=".", audio_only=False):
    if not validate_twitch_url(url):
        print(f"Warning: URL format check passed, but might not be standard Twitch VOD URL: {url}")

    # Check for twitch-dl
    if not shutil.which("twitch-dl"):
        print("Error: 'twitch-dl' command not found. Please install it (uv add twitch-dl).")
        sys.exit(1)

    print(f"Processing Twitch URL: {url}")
    
    # 1. Fetch Metadata
    info = get_twitch_info(url)
    if not info:
        print("Failed to retrieve video info.")
        sys.exit(1)

    title = info.get("title", f"Twitch_VOD_{info.get('id', 'unknown')}")
    description = info.get("description") # Can be None
    if description is None:
         description = "No description available."
    
    duration = info.get("lengthSeconds", 0)

    print(f"Found Title: {title}")
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

    # 2. Download via twitch-dl
    # twitch-dl download <url> -q source -o <file> --overwrite
    output_template = os.path.join(output_dir, "original.mp4")

    print(f"Downloading video '{title}' via twitch-dl...")
    
    cmd = [
        "twitch-dl", "download", url,
        "--quality", "source",
        "--output", output_template,
        "--overwrite"
    ]
    
    try:
        # Stream stdout to user so they see progress bar
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"twitch-dl download failed: {e}")
        sys.exit(1)

    if not os.path.exists(output_template):
        print("Error: Download finished but output file missing.")
        sys.exit(1)

    # 2.5 Audio Download (if requested)
    if audio_only:
        audio_template = os.path.join(output_dir, "audio.mp4")
        print(f"Downloading Audio Only '{title}'...")
        
        cmd_audio = [
            "twitch-dl", "download", url,
            "--quality", "audio_only",
            "--output", audio_template,
            "--overwrite"
        ]
        
        try:
            subprocess.run(cmd_audio, check=True)
            print(f"Audio saved to: {audio_template}")
        except subprocess.CalledProcessError as e:
            print(f"Audio download failed: {e}")
            # We don't exit here, as video might be successful

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
    if duration > 0 and duration < 180:
        print("\n[Auto-Transcribe] Video duration < 180s.")
        print("Starting transcription...")
        try:
            transcribe_video(
                input_file=output_template,
                output_file="zh.srt",
                translate_to_zh=True
            )
        except Exception as e:
            print(f"Transcription failed: {str(e)}")
    else:
        print(f"\nSkipping auto-transcription (only for < 180s).")

    print("\nDone!")

def main():
    parser = argparse.ArgumentParser(description="Twitch Downloader (twitch-dl)")
    parser.add_argument("url", help="Twitch VOD URL")
    parser.add_argument("--root_dir", default=".", help="Root directory to create video folder in (default: current directory)")
    parser.add_argument("--audio", action='store_true', default=False, help="Also download audio track as audio.mp4")
    args = parser.parse_args()

    download_video(args.url, root_dir=args.root_dir, audio_only=args.audio)

if __name__ == "__main__":
    main()
