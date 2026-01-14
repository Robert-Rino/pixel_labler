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

def main():
    parser = argparse.ArgumentParser(description="Twitch VOD Monitor")
    parser.add_argument("--channel_url", default="https://www.twitch.tv/zackrawrr", help="Twitch Channel URL")
    parser.add_argument("--memory_file", default="memory.txt", help="Path to memory file storing last timestamp")
    
    args = parser.parse_args()
    
    # 1. Get Latest VOD
    vod_info = get_latest_vod(args.channel_url)
    if not vod_info:
        sys.exit(1)
        
    # twitch-dl/yt-dlp timestamps are often Unix timestamps (float/int)
    # The 'url' field is the video URL
    latest_url = vod_info.get('url')
    # Use 'timestamp' or 'upload_date' for comparison. Timestamp is more precise.
    # But extract_flat might not have full timestamp. It usually has 'timestamp' if available.
    # For Twitch VODs flat extraction usually has url, title, id.
    # If flat extraction misses timestamp, we might need full extraction for that 1 video.
    
    # Let's check keys. If timestamp missing, we fetch full info for that single video (fast enough).
    # Actually, let's just use the ID or URL for uniqueness? 
    # But user asked for "uploadtime > memory".
    
    # Try fetch full info for the single video to get precise timestamp
    if 'timestamp' not in vod_info:
        print(f"Fetching full details for candidate: {latest_url}")
        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
            vod_info = ydl.extract_info(latest_url, download=False)
            
    latest_ts = vod_info.get('timestamp') # Unix timestamp
    latest_title = vod_info.get('title')
    
    if latest_ts is None:
        print("Could not determine timestamp for VOD.")
        sys.exit(1)
        
    print(f"Latest VOD: {latest_title} (TS: {latest_ts})")

    # 2. Read Memory
    memory_path = os.path.abspath(args.memory_file)
    last_ts = 0.0
    
    if os.path.exists(memory_path):
        try:
            with open(memory_path, 'r') as f:
                content = f.read().strip()
                if content:
                    last_ts = float(content)
        except ValueError:
            print("Invalid memory file content, defaulting to 0.")
    
    print(f"Last recorded TS: {last_ts}")
    
    # 3. Compare and Trigger
    # Using a small buffer just in case, or strict >
    if latest_ts > last_ts:
        print("New VOD detected! Triggering download...")
        
        # Trigger twitch_download.py
        # Assuming we are in the repo root or passing full path?
        # Script location:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        downloader_script = os.path.join(script_dir, "twitch_download.py")
        
        cmd = ["uv", "run", downloader_script, latest_url, "--root_dir", DOWNLOAD_DIR]
        
        try:
            # We run synchronously to ensure it finishes? Or maybe we want to detach?
            # User said "trigger", cron usually waits. Let's run and wait.
            subprocess.run(cmd, check=True)
            print("Download process completed successfully.")
            
            # 4. Update Memory
            # Only update if download succeeded
            with open(memory_path, 'w') as f:
                f.write(str(latest_ts))
            print(f"Updated memory with TS: {latest_ts}")
            
        except subprocess.CalledProcessError as e:
            print(f"Download script failed: {e}")
            # Do NOT update memory so we retry next time?
            sys.exit(1)
            
    else:
        print("No new VOD found.")

if __name__ == "__main__":
    main()
