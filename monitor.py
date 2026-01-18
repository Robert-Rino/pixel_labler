import os
import sys
import argparse
import subprocess
import datetime
import requests
import yt_dlp
import json
import time

DOWNLOAD_DIR = "/Users/nino/Repository/n8n/data"
DEFAULT_CHANNEL_URL = "https://www.twitch.tv/zackrawrr"
DEFAULT_MEMORY_FILE = "memory.txt"

def clean_filename(text):
    """Remove invalid characters for folder names"""
    import re
    if not text: return "Untitled"
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def is_vod_ready(url):
    """
    Check if the VOD is fully processed (ready for download) by inspecting the m3u8 manifest.
    Prevents downloading 'ghost' VODs (incomplete/live segments).
    """
    print(f"Checking VOD status for: {url}")
    
    # 1. Get m3u8 URL using yt-dlp
    ydl_opts = {
        'quiet': True,
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]', # Just need a stream url
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # force_generic_extractor=False is default
            # We want to get the direct stream URL
            info = ydl.extract_info(url, download=False)
            m3u8_url = info.get('url')
            
            if not m3u8_url:
                print("[!] Could not retrieve stream URL.")
                return False
    except Exception as e:
        print(f"[!] Error getting stream URL: {e}")
        return False

    # 2. Download the Manifest text
    print(f"Downloading manifest from: {m3u8_url}")
    try:
        r = requests.get(m3u8_url)
        r.raise_for_status()
        manifest_content = r.text
    except Exception as e:
        print(f"[!] Network error checking manifest: {e}")
        return False

    # 3. Analyze the Tags
    is_finalized = "#EXT-X-ENDLIST" in manifest_content
    
    if is_finalized:
        print("[+] VOD is ready (ENDLIST tag found).")
        return True
    else:
        print("[-] VOD is NOT ready (No ENDLIST tag).")
        return False

def get_m3u8_url(video_url, cookies_path):
    """Uses yt-dlp (Python API) to handle authentication and extract the raw m3u8 URL."""
    print(f"[*] Authenticating with yt-dlp using {cookies_path}...")
    
    ydl_opts = {
        'cookiefile': cookies_path,
        'format': 'best',
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get('url')
    except Exception as e:
        print(f"[!] Error using yt-dlp Python API: {e}")
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
    
    # 1. Parse Segments (Store duration and URL)
    # Structure: [ (duration_float, inf_line, url_line), ... ]
    segments = []
    header_lines = []
    
    # Simple state machine to parse the file
    is_header = True
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF"):
            is_header = False
            # Extract duration (e.g., #EXTINF:10.000,)
            try:
                dur_str = line.split(":")[1].split(",")[0]
                duration = float(dur_str)
            except:
                duration = 10.0 # Fallback default
            
            # The URL is the next line
            if i + 1 < len(lines):
                url_line = lines[i+1]
                segments.append((duration, line, url_line))
        elif is_header and not line.startswith("#EXTINF") and not line.strip() == "":
             # Keep header tags like #EXTM3U, #EXT-X-TARGETDURATION
             # But skip the URL lines that follow EXTINF (handled above)
             # And skip EndList if it exists (we will add it manually)
             if "#EXT-X-ENDLIST" not in line:
                 header_lines.append(line)

    total_segments = len(segments)
    if total_segments == 0:
        print("[!] Error: No segments found in manifest.")
        return None

    # 2. Calculate Start/End indices
    start_sec = start_min * 60
    end_sec = (start_min + duration_min) * 60 if duration_min else None
    
    current_time = 0.0
    start_index = 0
    end_index = total_segments

    # Check if we even reached the start time
    total_duration_sec = sum(s[0] for s in segments)
    if total_duration_sec < start_sec:
        print(f"[-] Not enough content yet. Total: {total_duration_sec/60:.2f}m, Required Start: {start_min}m")
        return None

    # Find Start Index
    current_time = 0.0
    for idx, (dur, _, _) in enumerate(segments):
        if current_time >= start_sec:
            start_index = idx
            break
        current_time += dur
        
    # Find End Index (if duration specified)
    if end_sec:
        # Check if we have enough content for the full duration
        required_end_sec = start_sec + (duration_min * 60)
        if total_duration_sec < required_end_sec:
             print(f"[-] Not enough content for full chunk. Total: {total_duration_sec/60:.2f}m, Required End: {required_end_sec/60:.2f}m")
             return None

        current_time = 0.0 
        accumulated_dur = 0.0 # From start_index
        
        # Calculate offset time to reach start_index exactly? 
        # Actually segments are atomic. We approximate.
        
        # Recalculate accumulation strictly from chosen start_index
        for idx in range(start_index, total_segments):
            accumulated_dur += segments[idx][0]
            if accumulated_dur >= (duration_min * 60):
                end_index = idx + 1
                break
    
    selected_segments = segments[start_index:end_index]
    
    print(f"\n--- Slicing Report ---")
    print(f"Total Available:  {total_segments} chunks")
    print(f"Start Time:       {start_min} min (Chunk #{start_index})")
    print(f"Duration Target:  {duration_min if duration_min else 'Until End'} min")
    print(f"Chunks Selected:  {len(selected_segments)}")
    
    if len(selected_segments) == 0:
        return None

    # 3. Construct New Manifest
    new_lines = list(header_lines)
    
    for dur, inf, url in selected_segments:
        new_lines.append(inf)
        
        # Absolute URL Fix
        if not url.startswith("http"):
            new_lines.append(base_url + url)
        else:
            new_lines.append(url)
            
    # THE MAGIC KEY: Force it to be a static VOD
    new_lines.append("#EXT-X-ENDLIST")
    
    return "\n".join(new_lines)

def get_latest_vod(channel_url):
    """
    Fetch the latest VOD metadata from the Twitch channel using yt-dlp.
    We target the 'videos' tab to get VODs.
    """
    # Twitch channel URL for VODs usually looks like .../videos?filter=archives&sort=time
    # But yt-dlp might handle the main channel URL and pick latest.
    # Best to be specific if possible or rely on yt-dlp's playlist handling (channel is a playlist).
    
    # We want top 1 video (latest)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True, # Faster, just get metadata list
        'playlistend': 1,     # Only get the latest one
    }

    # "https://www.twitch.tv/zackrawrr/videos" might be safer to ensure we get videos, not live
    # But yt-dlp 'https://www.twitch.tv/CHANNEL' checks live status.
    # 'https://www.twitch.tv/CHANNEL/videos' is the videos tab.
    
    target_url = channel_url
    if not target_url.endswith('/videos'):
         target_url = target_url.rstrip('/') + '/videos?filter=archives&sort=time'

    print(f"Checking for latest VOD at: {target_url}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(target_url, download=False)
        except Exception as e:
            print(f"Error fetching channel info: {e}")
            return None

        if 'entries' in info:
            entries = list(info['entries'])
            if not entries:
                print("No videos found.")
                return None
            return entries[0] # Latest video
        else:
            # Might be a single video if URL was specific, but for channel it should be entries
            return info

def load_memory(memory_path):
    if not os.path.exists(memory_path):
        return {"last_ts": 0.0, "vod_url": "", "downloaded_hours": 0}
    
    try:
        with open(memory_path, 'r') as f:
            content = f.read().strip()
            # Try parsing as JSON first
            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError:
                # Fallback to old format (just float timestamp)
                return {"last_ts": float(content), "vod_url": "", "downloaded_hours": 0}
    except Exception as e:
        print(f"Error loading memory: {e}")
        return {"last_ts": 0.0, "vod_url": "", "downloaded_hours": 0}

def save_memory(memory_path, data):
    try:
        with open(memory_path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving memory: {e}")

def get_new_video(channel_url=DEFAULT_CHANNEL_URL, memory_file=DEFAULT_MEMORY_FILE, update_memory=True):
    """
    Checks for a new VOD or new chunks of current VOD.
    """
    memory_path = os.path.abspath(memory_file)
    memory = load_memory(memory_path)
    
    # 1. Get Latest VOD
    vod_info = get_latest_vod(channel_url)
    if not vod_info:
        return None

    latest_url = vod_info.get('url')
    
    # Try fetch full info for the single video to get precise timestamp
    if 'timestamp' not in vod_info:
        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
            try:
                vod_info = ydl.extract_info(latest_url, download=False)
            except:
                pass

    uploader = vod_info.get('uploader', 'Unknown')
    upload_date = vod_info.get('upload_date', '00000000') # YYYYMMDD
    last_ts = vod_info.get('timestamp') # Unix timestamp

    if last_ts:
        dt = datetime.datetime.fromtimestamp(last_ts)
        date_str = dt.strftime("%Y-%m-%dT%H_%M_%S")
    else:
        print("Could not determine timestamp for VOD.")
        return None
    
    title = f'Twitch_VOD_{uploader}_{date_str}'

    # Logic:
    # 1. If New VOD (last_ts > memory.last_ts):
    #    - Reset downloaded_hours = 0
    #    - Check if VOD is ready (is_vod_ready)
    #      - If Ready: Return URL to download full.
    #      - If Not Ready: Check if Hour 1 is ready.
    #        - If Yes: Download Hour 1.
    #        - If No: Wait.
    
    # 2. If Same VOD (last_ts == memory.last_ts):
    #    - Check current downloaded_hours.
    #    - Check if Next Hour (downloaded_hours + 1) is ready.
    #      - If Yes: Download Next Hour.
    
    current_ts = memory.get("last_ts", 0.0)
    downloaded_hours = memory.get("downloaded_hours", 0)
    
    action_type = None # "FULL", "CHUNK", "NONE"
    target_hour_start = 0
    
    if last_ts > current_ts:
        print(f"[{datetime.datetime.now()}] New VOD detected: {title}")
        # Reset state for new VOD
        downloaded_hours = 0 
        
        if is_vod_ready(latest_url):
            print("VOD is fully ready.")
            action_type = "FULL"
        else:
            print("VOD is live/incomplete. Checking for Hour 1...")
            action_type = "CHUNK"
            target_hour_start = 0 # 0th hour (0-60 min) -> Hour 1

    elif abs(last_ts - current_ts) < 600: # Same VOD (allow small jitter)
        # Check for next chunk
        print(f"Checking updates for current VOD: {title} (Downloaded: {downloaded_hours}h)")
        if not is_vod_ready(latest_url):
             action_type = "CHUNK"
             target_hour_start = downloaded_hours
        else:
             # VOD finished? Maybe download the rest?
             # For now, user request focused on incremental. 
             # If we already downloaded partial, full download might duplicate.
             # Ignoring this complex case for now, assuming we continue chunking or user manually handles.
             pass
    
    if action_type == "CHUNK":
        # Process Chunk Download
        # Need cookies
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        m3u8_url = get_m3u8_url(latest_url, cookies_path)
        
        if m3u8_url:
            # Check if next hour is available
            # start_min = target_hour_start * 60
            # duration_min = 60
            
            new_manifest = parse_and_slice_manifest(m3u8_url, start_min=target_hour_start*60, duration_min=60)
            
            if new_manifest:
                print(f"[!] Chunk {target_hour_start+1} (Hour {target_hour_start}-{target_hour_start+1}) is ready!")
                
                if update_memory:
                    # Create Folder Structure
                    safe_title = clean_filename(title)
                    safe_title = safe_title[:240] 
                    video_dir = os.path.join(DOWNLOAD_DIR, safe_title)
                    
                    if not os.path.exists(video_dir):
                        os.makedirs(video_dir, exist_ok=True)
                        print(f"Created chunk directory: {video_dir}")
                    
                    # 1. Save Manifest
                    chunk_filename = f"chunk_{target_hour_start + 1}.m3u8"
                    chunk_path = os.path.join(video_dir, chunk_filename)
                        
                    with open(chunk_path, 'w') as f:
                        f.write(new_manifest)
                        
                    print(f"Saved chunk manifest: {chunk_path}")
                    
                    # 2. Trigger Download logic
                    output_name = f"{safe_title}_hour_{target_hour_start+1}.mp4"
                    output_path = os.path.join(video_dir, output_name)
                    
                    try:
                        print(f"Downloading chunk to: {output_path}")
                        
                        ydl_opts_chunk = {
                            'cookiefile': cookies_path,
                            'outtmpl': output_path,
                            'quiet': True,
                        }
                        
                        with yt_dlp.YoutubeDL(ydl_opts_chunk) as ydl:
                            ydl.download([chunk_path])
                        
                        # Update Memory
                        memory["last_ts"] = last_ts
                        memory["vod_url"] = latest_url
                        memory["downloaded_hours"] = target_hour_start + 1
                        save_memory(memory_path, memory)
                        print(f"Memory updated: {downloaded_hours} -> {target_hour_start + 1} hours")
                        
                        return "CHUNK_DOWNLOADED" # Signal main to skip generic download
                        
                    except Exception as e:
                        print(f"Chunk download failed: {e}")
                        return None
            else:
                 print("Next hour chunk not ready yet.")
    
    elif action_type == "FULL":
        # Update memory upfront? Or after?
        # If we return URL, main() handles download.
        # We should assume main() succeeds?
        if update_memory:
            memory["last_ts"] = last_ts
            memory["vod_url"] = latest_url
            memory["downloaded_hours"] = 999 # completed
            save_memory(memory_path, memory)
            
        return latest_url

    return None

def main():
    parser = argparse.ArgumentParser(description="Twitch VOD Monitor")
    parser.add_argument("--channel_url", default=DEFAULT_CHANNEL_URL, help="Twitch Channel URL")
    parser.add_argument("--memory_file", default=DEFAULT_MEMORY_FILE, help="Path to memory file storing last timestamp")
    parser.add_argument("--download", action="store_true", help="If set, triggers download and updates memory.")
    
    args = parser.parse_args()
    
    # Check for new video / chunks
    result = get_new_video(args.channel_url, args.memory_file, update_memory=args.download)
    
    if result and result != "CHUNK_DOWNLOADED":
        # result is a URL (Full VOD)
        if args.download:
            print(f"Triggering FULL download for: {result}")
            
            # Script location:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            downloader_script = os.path.join(script_dir, "twitch_download.py")
            
            cmd = ["uv", "run", downloader_script, result, "--root_dir", DOWNLOAD_DIR]
            
            try:
                subprocess.run(cmd, check=True)
                print("Download process completed successfully.")
                
            except subprocess.CalledProcessError as e:
                print(f"Download script failed: {e}")
                sys.exit(1)
        else:
            print(f"Found new VOD: {result}")
            print("Download skipped (Peek mode).")
    elif result == "CHUNK_DOWNLOADED":
        print("Chunk processing cycle completed.")



if __name__ == "__main__":
    main()
