import requests
import json
import os
import time
import sys

def download_chat(video_url_or_id, output_path, start_min=None, duration_min=None):
    """
    Downloads Twitch chat logs using the GQL API (same approach as lay295/TwitchDownloader).
    Handles pagination and maps output to a format compatible with analyzer.py.
    """
    # Extract video ID
    video_id = video_url_or_id
    if "/" in video_url_or_id:
        video_id = video_url_or_id.rstrip("/").split("/")[-1]
    
    # Check if video_id is just numbers
    if not video_id.isdigit():
        print(f"Error: Could not extract a valid video ID from {video_url_or_id}")
        return False

    url = "https://gql.twitch.tv/gql"
    client_id = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"
    sha256_hash = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"
    
    headers = {
        "Client-Id": client_id,
        "Content-Type": "application/json"
    }

    start_seconds = (start_min * 60) if start_min is not None else 0
    end_seconds = (start_seconds + (duration_min * 60)) if duration_min is not None else float('inf')

    all_comments = []
    cursor = None
    
    print(f"[*] Starting chat download for video {video_id}...")
    if start_min is not None:
        print(f"[*] Filtering for range: {start_min}m to {start_min + (duration_min or 0)}m")

    while True:
        variables = {
            "videoID": video_id
        }
        
        if cursor:
            variables["cursor"] = cursor
        else:
            variables["contentOffsetSeconds"] = start_seconds

        payload = [{
            "operationName": "VideoCommentsByOffsetOrCursor",
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256_hash
                }
            }
        }]

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                data = data[0]
            
            if "errors" in data:
                print(f"[!] GQL Error: {data['errors']}")
                break
                
            video_data = data.get("data", {}).get("video", {})
            if not video_data:
                print("[!] No video data found in response.")
                break
                
            comments_data = video_data.get("comments", {})
            edges = comments_data.get("edges", [])
            
            if not edges:
                break
                
            last_offset = 0
            for edge in edges:
                node = edge.get("node", {})
                offset = node.get("contentOffsetSeconds", 0)
                last_offset = offset
                
                # Check if we passed the end_seconds (if specified)
                if offset > end_seconds:
                    break
                
                if offset >= start_seconds:
                    # Map to format expected by analyzer.py (rechat-like)
                    all_comments.append({
                        "content_offset_seconds": offset,
                        "message": node.get("message", {}),
                        "commenter": node.get("commenter", {})
                    })

            # Check if we broke early due to end_seconds
            if last_offset > end_seconds:
                break
                
            # Get cursor for next page
            page_info = comments_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = edges[-1].get("cursor")
                # Simple progress report
                print(f"[*] Collected {len(all_comments)} comments... (Current time: {int(last_offset//60)}m)", end='\r')
            else:
                break
                
            # Rate limiting / polite pause
            time.sleep(0.1)

        except Exception as e:
            print(f"\n[!] Error during download: {e}")
            # Could implement retry here
            break

    print(f"\n[*] Download complete. Total comments: {len(all_comments)}")
    
    if not all_comments:
        print("[!] No comments found for the specified range.")
        return False

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_comments, f, ensure_ascii=False, indent=2)
        print(f"[*] Chat log saved to {output_path}")
        return True
    except Exception as e:
        print(f"[!] Error saving chat file: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python chat_utils.py <video_url_or_id> <output_path> [start_min] [duration_min]")
    else:
        v_id = sys.argv[1]
        out = sys.argv[2]
        s_min = int(sys.argv[3]) if len(sys.argv) > 3 else None
        d_min = int(sys.argv[4]) if len(sys.argv) > 4 else None
        download_chat(v_id, out, s_min, d_min)
