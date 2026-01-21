import os
import sys
import argparse
import re
import subprocess
import shutil
import json
import requests
import pathlib
import transcript
import n8n
import yt_dlp
import datetime

def clean_filename(text):
    """Remove invalid characters for folder names"""
    if not text: return "Untitled"
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def get_m3u8_url(video_url, cookies_path=None):
    """Uses yt-dlp to extract the raw m3u8 URL."""
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        'quiet': True,
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get('url')
    except Exception as e:
        print(f"[!] Error getting m3u8 URL: {e}")
        return None

def parse_and_slice_manifest(manifest_url, start_min, duration_min):
    """Downloads manifest, parses segments, slices them, and returns new content or None if not ready."""
    print(f"[*] Fetching Manifest for slicing: {manifest_url}")
    
    try:
        r = requests.get(manifest_url)
        r.raise_for_status()
        content = r.text
    except Exception as e:
        print(f"[!] Network Error: {e}")
        return None

    lines = content.splitlines()
    base_url = manifest_url.rsplit('/', 1)[0] + '/'
    
    segments = []
    header_lines = []
    
    is_header = True
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            is_header = False
            try:
                dur_str = line.split(":")[1].split(",")[0]
                duration = float(dur_str)
            except:
                duration = 10.0
            
            if i + 1 < len(lines):
                url_line = lines[i+1]
                segments.append((duration, line, url_line))
        elif is_header and not line.startswith("#EXTINF") and not line.strip() == "":
             if "#EXT-X-ENDLIST" not in line:
                 header_lines.append(line)

    total_segments = len(segments)
    if total_segments == 0:
        return None

    start_sec = start_min * 60
    end_sec = (start_min + duration_min) * 60 if duration_min else None
    
    # Validation
    total_duration_sec = sum(s[0] for s in segments)
    if total_duration_sec < start_sec:
        print(f"[-] Not enough content yet. Total: {total_duration_sec/60:.2f}m, Required Start: {start_min}m")
        return None

    current_time = 0.0
    start_index = 0
    end_index = total_segments
    
    for idx, (dur, _, _) in enumerate(segments):
        if current_time >= start_sec:
            start_index = idx
            break
        current_time += dur
        
    if end_sec:
        required_end_sec = start_sec + (duration_min * 60)
        # We allow a little flexibility/jitter, but generally strict
        if total_duration_sec < required_end_sec: 
             print(f"[-] Not enough content for full chunk. Total: {total_duration_sec/60:.2f}m, Required End: {required_end_sec/60:.2f}m")
             return None

        current_time = 0.0 
        accumulated_dur = 0.0
        for idx in range(start_index, total_segments):
            accumulated_dur += segments[idx][0]
            if accumulated_dur >= (duration_min * 60):
                end_index = idx + 1
                break
    
    selected_segments = segments[start_index:end_index]
    
    if len(selected_segments) == 0:
        return None

    new_lines = list(header_lines)
    for dur, inf, url in selected_segments:
        new_lines.append(inf)
        if not url.startswith("http"):
            new_lines.append(base_url + url)
        else:
            new_lines.append(url)
            
    new_lines.append("#EXT-X-ENDLIST")
    return "\n".join(new_lines)

def download_video(url, root_dir=".", audio=True, start_min=None, duration_min=None):
    print(f"Processing Twitch URL: {url} (Start: {start_min}, Dur: {duration_min})")
    
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

    uploader = info.get('uploader', 'Unknown')
    upload_date = info.get('upload_date', '00000000') 
    timestamp = info.get('timestamp')
    
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
    
    safe_title = clean_filename(title)
    safe_title = safe_title[:240] 

    root_dir = os.path.abspath(root_dir)
    video_dir = os.path.join(root_dir, safe_title)
    trigger_folder = safe_title
    
    # Chunk Subfolder Logic
    if start_min is not None and duration_min is not None:
        chunk_name = f"chunk-{start_min}-{start_min + duration_min}"
        output_dir = os.path.join(video_dir, chunk_name)
        trigger_folder = f'{safe_title}/{chunk_name}'
    else:
        output_dir = video_dir
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    else:
        print(f"Using existing directory: {output_dir}")

    # 2. Download via yt-dlp
    output_original = os.path.join(output_dir, "original.mp4")
    output_audio = os.path.join(output_dir, "audio.mp4")
    srt_output = os.path.join(output_dir, "transcript.srt")
    
    # If Slicing is enabled
    dl_source = url # Default
    
    if start_min is not None and duration_min is not None:
        print("--- Slicing Mode Active ---")
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        m3u8_url = get_m3u8_url(url, cookies_path)
        
        if not m3u8_url:
            print("[!] Failed to get m3u8 url for slicing.")
            return

        new_manifest = parse_and_slice_manifest(m3u8_url, start_min, duration_min)
        if not new_manifest:
             print("[!] Slicing failed (maybe not ready yet).")
             return

        chunk_manifest_path = os.path.join(output_dir, "chunk.m3u8")
        with open(chunk_manifest_path, 'w') as f:
            f.write(new_manifest)
        print(f"Sliced manifest saved to: {chunk_manifest_path}")
        dl_source = pathlib.Path(chunk_manifest_path).as_uri()
        print(dl_source)

    # 2.1 Video Download (480p)
    if os.path.exists(output_original):
        print("Original video already exists. Skipping download.")
    else:
        print(f"Downloading video '{title}' (480p) via yt-dlp...")
        ydl_opts_video = {
            'format': 'best',
            'outtmpl': output_original,
            'concurrent_fragment_downloads': 16, 
            'external_downloader': {'m3u8': 'native'},
            'retries': 10,
            ' fragment_retries': 10,
            'ignoreerrors': True,
            'enable_file_urls': True,
        }
        
        # Add cookies if needed for local m3u8? usually not if local file, 
        # but if the segments inside are protected or generic check needs it.
        # But for 'dl_source' which is a local file, yt-dlp just parses it.
        # The segments inside are HTTP URLs. 
        # If segments need auth, we might need cookies.
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookies_path):
             ydl_opts_video['cookiefile'] = cookies_path 

        try:
            with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
                ydl.download([dl_source])
        except Exception as e:
            print(f"Video download failed: {e}")
            sys.exit(1)

        if not os.path.exists(output_original):
            print("Error: Video download finished but output file missing.")
            sys.exit(1)

    # 2.2 Audio Download (Direct Audio_Only)
    if audio and not os.path.exists(output_audio):
        # Extract Audio from Video using ffmpeg
        ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", output_original,
                '-vn', 
                '-acodec', 'copy',
                output_audio,
            ]
            
        print(f"Extracting audio from: {output_original}...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"FFmpeg error:\\n{result.stderr}")
            # Don't return, maybe try to continue? But audio is needed for transcript.
            # If audio extraction fails, we probably can't transcribe.
            pass

    # 3. Create Metadata File
    metadata_path = os.path.join(output_dir, "metadata.md")
    if not os.path.exists(metadata_path):
        print(f"Writing metadata to: {metadata_path}")
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write("```\n")
            f.write(f"Source: {url}\n")
            f.write(f"Title: {title}\n")
            f.write(f"Original Title: {original_title}\n")
            f.write(f"Description: {description}\n")
            # Add Chunk Info
            if start_min is not None:
                f.write(f"Chunk Start: {start_min}m\n")
                f.write(f"Chunk Duration: {duration_min}m\n")
            f.write("```\n")
    else:
        print("Metadata file exists.")

    print(f"Output saved in: {output_dir}")

    # 4. Auto-Transcribe
    if not os.path.exists(srt_output):
        print("Starting transcription...")
        try:
            transcript.transcribe_video(
                input_file=output_audio,
                output_file=srt_output,
            )
        except Exception as e:
            print(f"Transcription failed: {str(e)}")

        transcript.split_srt_by_hour(srt_output)
    else:
        print("Transcript already exists.")

    # 5. N8N Trigger    
    try:
        n8n.trigger('analyze', trigger_folder)
    except Exception as e:
        print(f"N8N Trigger failed: {e}")

    print("\nDone!")

def main():
    parser = argparse.ArgumentParser(description="Twitch Downloader (via yt-dlp)")
    parser.add_argument("url", help="Twitch VOD URL")
    parser.add_argument("--root_dir", default=".", help="Root directory to create video folder in (default: current directory)")
    parser.add_argument("--audio", action='store_true', default=True, help="Extract audio (default: True)")
    parser.add_argument("--start_min", type=int, default=None, help="Start time in minutes for slicing")
    parser.add_argument("--duration_min", type=int, default=None, help="Duration in minutes for slicing")
    args = parser.parse_args()

    download_video(args.url, root_dir=args.root_dir, audio=args.audio, start_min=args.start_min, duration_min=args.duration_min)

if __name__ == "__main__":
    main()
