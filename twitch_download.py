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
    output_template = os.path.join(output_dir, "original.mp4")
    audio_template = os.path.join(output_dir, "audio.mp4")
    srt_output = os.path.join(output_dir, "transcript.srt")

    # 2.1 Video Download (480p)
    print(f"Downloading video '{title}' (480p) via yt-dlp...")
    ydl_opts_video = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'concurrent_fragment_downloads': 10,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"Video download failed: {e}")
        sys.exit(1)

    if not os.path.exists(output_template):
        print("Error: Video download finished but output file missing.")
        sys.exit(1)

    # 2.2 Audio Download (Direct Audio_Only)
    if audio:
        print(f"Downloading audio '{title}' (Audio Only) via yt-dlp...")
        ydl_opts_audio = {
            'format': 'bestaudio/best',
            'outtmpl': audio_template,
            'concurrent_fragment_downloads': 10,
            # Ensure we get an m4a/mp4 audio file
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp4',
            }],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                ydl.download([url])
            # yt-dlp with aac postprocessor might append .aac or .m4a. 
            # We forced outtmpl to audio.mp4, but postprocessor might change extension.
            # Let's check.
            # Actually, standard behavior: if outtmpl ends in .mp4, it might keep it.
            # But let's verify if file exists or if it has another extension.
            base_audio, _ = os.path.splitext(audio_template)
            found_audio = False
            for ext in ['.mp4', '.m4a', '.aac']:
                if os.path.exists(base_audio + ext):
                    if base_audio + ext != audio_template:
                        shutil.move(base_audio + ext, audio_template)
                    found_audio = True
                    break
            
            if not found_audio:
                 print(f"Warning: Audio file not found at expected path: {audio_template}")
            else:
                 print(f"Audio saved to: {audio_template}")

        except Exception as e:
            print(f"Audio download failed: {e}")


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
            input_file=audio_template,
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
