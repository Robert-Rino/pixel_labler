import os
import sys
import argparse
import subprocess
import datetime
import yt_dlp

DOWNLOAD_DIR = "~/Repository/n8n/data"

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

DEFAULT_CHANNEL_URL = "https://www.twitch.tv/zackrawrr"
DEFAULT_MEMORY_FILE = "memory.txt"

def get_new_video(channel_url=DEFAULT_CHANNEL_URL, memory_file=DEFAULT_MEMORY_FILE, update_memory=True):
    """
    Checks for a new VOD.
    If found and newer than memory:
      - If update_memory=True: updates memory and returns the VOD URL.
      - If update_memory=False: returns the VOD URL (peek mode).
    Otherwise returns None.
    """
    # 1. Get Latest VOD
    vod_info = get_latest_vod(channel_url)
    if not vod_info:
        return None
        
    latest_url = vod_info.get('url')
    
    # Try fetch full info for the single video to get precise timestamp
    if 'timestamp' not in vod_info:
        # print(f"Fetching full details for candidate: {latest_url}")
        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
            vod_info = ydl.extract_info(latest_url, download=False)
            
    latest_ts = vod_info.get('timestamp') # Unix timestamp
    latest_title = vod_info.get('title')
    
    if latest_ts is None:
        print("Could not determine timestamp for VOD.")
        return None
        
    # print(f"Latest VOD: {latest_title} (TS: {latest_ts})")

    # 2. Read Memory
    memory_path = os.path.abspath(memory_file)
    last_ts = 0.0
    
    if os.path.exists(memory_path):
        try:
            with open(memory_path, 'r') as f:
                content = f.read().strip()
                if content:
                    last_ts = float(content)
        except ValueError:
            print("Invalid memory file content, defaulting to 0.")
    
    # print(f"Last recorded TS: {last_ts}")
    
    # 3. Compare
    if latest_ts > last_ts:
        print(f"[{datetime.datetime.now()}] New VOD detected: {latest_title}")
        
        if update_memory:
            # 4. Update Memory
            try:
                with open(memory_path, 'w') as f:
                    f.write(str(latest_ts))
                print(f"Updated memory with TS: {latest_ts}")
            except Exception as e:
                print(f"Failed to update memory file: {e}")
        else:
            print("Memory update skipped (dry run).")
            
        return latest_url
            
    else:
        # print("No new VOD found.")
        return None

def main():
    parser = argparse.ArgumentParser(description="Twitch VOD Monitor")
    parser.add_argument("--channel_url", default=DEFAULT_CHANNEL_URL, help="Twitch Channel URL")
    parser.add_argument("--memory_file", default=DEFAULT_MEMORY_FILE, help="Path to memory file storing last timestamp")
    parser.add_argument("--download", action="store_true", help="If set, triggers download and updates memory.")
    
    args = parser.parse_args()
    
    # Only update memory if we intend to download
    new_url = get_new_video(args.channel_url, args.memory_file, update_memory=args.download)
    
    if new_url:
        if args.download:
            print("Triggering download...")
            
            # Script location:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            downloader_script = os.path.join(script_dir, "twitch_download.py")
            
            cmd = ["uv", "run", downloader_script, new_url, "--root_dir", DOWNLOAD_DIR]
            
            try:
                # We run synchronously to ensure it finishes? Or maybe we want to detach?
                # User said "trigger", cron usually waits. Let's run and wait.
                subprocess.run(cmd, check=True)
                print("Download process completed successfully.")
                
            except subprocess.CalledProcessError as e:
                print(f"Download script failed: {e}")
                sys.exit(1)
        else:
            print(f"Found new VOD: {new_url}")
            print("Download skipped. Use --download to trigger download and update memory.")


if __name__ == "__main__":
    main()
