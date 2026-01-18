import os
import sys
import argparse

import datetime
import requests
import yt_dlp
import json

import twitch_download

DOWNLOAD_DIR = "/Users/nino/Repository/n8n/data"
DEFAULT_CHANNEL_URL = "https://www.twitch.tv/zackrawrr"
DEFAULT_MEMORY_FILE = "memory.txt"

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
                return {"last_ts": float(content), "vod_url": "", "downloaded_chunks": 0, "total_chunks": 0}
    except Exception as e:
        print(f"Error loading memory: {e}")
        return {"last_ts": 0.0, "vod_url": "", "downloaded_chunks": 0, "total_chunks": 0}

def save_memory(memory_path, data):
    try:
        with open(memory_path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving memory: {e}")

def get_new_video(channel_url=DEFAULT_CHANNEL_URL, memory_file=DEFAULT_MEMORY_FILE, update_memory=True, chunk_size=60):
    """
    Checks for a new VOD or new chunks of current VOD.
    If update_memory is True, it enforces chunked downloading logic.
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
    downloaded_chunks = memory.get("downloaded_chunks", 0)
    
    action_type = None # "CHUNK", "NONE" (Full is deprecated for download mode)
    target_chunk_index = 0
    
    # 1. Start / Reset Logic
    if last_ts > current_ts:
        print(f"[{datetime.datetime.now()}] New VOD detected: {title}")
        downloaded_chunks = 0 
        target_chunk_index = 0
        action_type = "CHUNK"
        
    elif abs(last_ts - current_ts) < 600: # Same VOD
        print(f"Checking updates for current VOD: {title} (Downloaded Chunks: {downloaded_chunks})")
        target_chunk_index = downloaded_chunks
        action_type = "CHUNK"
    

    # 2. Execution Logic
    if action_type == "CHUNK":
        video_duration = vod_info.get('duration')
        
        total_chunks = 0
        if video_duration:
            import math
            total_chunks = math.ceil(video_duration / 60 / chunk_size)
        else:
            # If live, duration might be None or growing. 
            # We can treat total_chunks as infinite or unknown.
            total_chunks = 999999
            
        print(f"VOD Duration: {video_duration}s -> Total Chunks: {total_chunks}")
        
        # Check against Memory
        # If we have already downloaded >= total_chunks, stop.
        # BUT for LIVE videos, total_chunks keeps increasing (or is unknown).
        # So invalid check for live. 
        # Only valid if VOD is finalized (ENDLIST).
        
        if is_vod_ready(latest_url):
            if downloaded_chunks >= total_chunks:
                print(f"All chunks downloaded ({downloaded_chunks}/{total_chunks}).")
                return None
        
        if not update_memory:
            # Peek mode
            if last_ts > current_ts:
                return latest_url 
            else:
                return None # Same VOD
        
        # Download Mode
        target_chunk_index = downloaded_chunks
        start_min = target_chunk_index * chunk_size
        duration_min = chunk_size
        
        # Check if this chunk is theoretically within current duration?
        # If live, we just rely on manifest readiness.
        
        cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        m3u8_url = twitch_download.get_m3u8_url(latest_url, cookies_path)
        
        if m3u8_url:
            # Check availability using slice check
            new_manifest = twitch_download.parse_and_slice_manifest(m3u8_url, start_min=start_min, duration_min=duration_min)
            
            if new_manifest:
                print(f"[!] Chunk {target_chunk_index} ({start_min}-{start_min+duration_min}m) is ready!")
                print("Triggering chunk download via twitch_download.py...")
                
                try:
                    twitch_download.download_video(
                        latest_url,
                        root_dir=DOWNLOAD_DIR,
                        start_min=start_min,
                        duration_min=duration_min
                    )
                    print("Chunk download process completed successfully.")
                    
                    # Update Memory
                    memory["last_ts"] = last_ts
                    memory["vod_url"] = latest_url
                    memory["downloaded_chunks"] = target_chunk_index + 1
                    memory["total_chunks"] = total_chunks # Store target/total
                    save_memory(memory_path, memory)
                    print(f"Memory updated: {downloaded_chunks} -> {target_chunk_index + 1} chunks (Total: {total_chunks})")
                    return "CHUNK_DOWNLOADED"
                    
                except Exception as e:
                    print(f"Chunk download failed: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
            else:
                 print(f"Chunk {target_chunk_index} not ready yet.")

    
    return None

def main():
    parser = argparse.ArgumentParser(description="Twitch VOD Monitor")
    parser.add_argument("--channel_url", default=DEFAULT_CHANNEL_URL, help="Twitch Channel URL")
    parser.add_argument("--memory_file", default=DEFAULT_MEMORY_FILE, help="Path to memory file storing last timestamp")
    parser.add_argument("--download", action="store_true", help="If set, triggers download and updates memory.")
    parser.add_argument("--chunk_size", type=int, default=60, help="Chunk size in minutes (default: 60)")
    
    args = parser.parse_args()
    
    # Check for new video / chunks
    result = get_new_video(args.channel_url, args.memory_file, update_memory=args.download, chunk_size=args.chunk_size)
    
    if result == "CHUNK_DOWNLOADED":
        print("Chunk processing cycle completed.")
    elif result and result != "CHUNK_DOWNLOADED":
         # This usually means PEEK mode found a URL
         print(f"Found new VOD available: {result}")

if __name__ == "__main__":
    main()
