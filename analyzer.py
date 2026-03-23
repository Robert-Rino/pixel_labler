import subprocess
import numpy as np
import os
import json

def extract_audio_peaks(video_path, threshold_factor=2.0, window_size=1.0, sample_rate=16000):
    """
    Extracts timestamps where audio energy exceeds a rolling average threshold.
    """
    # Use ffmpeg to extract mono audio stream to stdout
    cmd = [
        "ffmpeg", "-i", video_path,
        "-f", "s16le", "-ac", "1", "-ar", str(sample_rate),
        "-"
    ]
    
    # Run ffmpeg process
    # We pipe stderr to DEVNULL to avoid cluttering output
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    samples_per_window = int(sample_rate * window_size)
    bytes_per_sample = 2  # s16le is 2 bytes
    chunk_size = samples_per_window * bytes_per_sample
    
    rms_values = []
    timestamps = []
    
    # Read audio in window-sized chunks
    while True:
        data = process.stdout.read(chunk_size)
        if not data:
            break
        
        # Convert byte data to numpy array
        # Ensure we have a complete chunk, or handle the partial chunk
        audio_chunk = np.frombuffer(data, dtype=np.int16)
        
        if len(audio_chunk) == 0:
            break
            
        # Calculate RMS for this chunk
        # RMS = sqrt(mean(squares))
        # Note: audio_chunk could be large, numpy is efficient
        rms = np.sqrt(np.mean(np.square(audio_chunk.astype(np.float32))))
        rms_values.append(rms)
        
        # Timestamp is the middle or start of the chunk
        # Current index in rms_values * window_size
        timestamps.append((len(rms_values) - 1) * window_size)
        
    process.stdout.close()
    process.wait()
    
    if not rms_values:
        return []
    
    # Calculate rolling average of RMS values
    # We can use a simple average over the whole file or a local rolling average
    # Given the user says "e.g., 2.0 * rolling_average", I'll use a local window if possible
    # but for simplicity, let's start with a global average or a 10s window rolling average
    
    rms_array = np.array(rms_values)
    
    # Local rolling average with a window of 10 samples (10 seconds)
    rolling_window = 10
    rolling_avg = np.zeros_like(rms_array)
    for i in range(len(rms_array)):
        start = max(0, i - rolling_window // 2)
        end = min(len(rms_array), i + rolling_window // 2 + 1)
        rolling_avg[i] = np.mean(rms_array[start:end])
    
    # Identify peaks: RMS > factor * rolling_avg
    peaks = []
    for i in range(len(rms_array)):
        if rms_array[i] > threshold_factor * rolling_avg[i]:
            score = rms_array[i] / max(rolling_avg[i], 1e-6)
            peaks.append((float(timestamps[i]), float(score)))
            
    return peaks

def analyze_chat_velocity(json_path, window_size=10, threshold_factor=1.5):
    """
    Parses rechat.json and identifies spikes in weighted chat velocity.
    """
    if not os.path.exists(json_path):
        return []

    with open(json_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            # Handle possible line-by-line JSON format if yt-dlp produces it
            f.seek(0)
            data = []
            for line in f:
                if line.strip():
                    data.append(json.loads(line))

    if not data:
        return []

    # Emotes with 2.0x weight
    emotes = {"Pog", "LUL", "KEKW", "OMEGALUL", "!!!"}
    
    # Calculate weighted count for each message
    weighted_messages = []
    max_time = 0
    for entry in data:
        # Some formats might have "content_offset_seconds" directly, 
        # others might be nested or have different names.
        # Based on yt-dlp rechat format:
        timestamp = entry.get("content_offset_seconds")
        if timestamp is None:
            # Fallback for other potential formats
            timestamp = entry.get("offset", 0)
            
        message_obj = entry.get("message", {})
        if isinstance(message_obj, dict):
            message = message_obj.get("body", "")
        else:
            message = str(entry.get("comment", "")) # Fallback

        weight = 1.0
        for emote in emotes:
            if emote.lower() in message.lower():
                weight = 2.0
                break
        
        weighted_messages.append((timestamp, weight))
        if timestamp > max_time:
            max_time = timestamp

    # Window the messages
    num_windows = int(max_time // window_size) + 1
    window_counts = np.zeros(num_windows)
    
    for timestamp, weight in weighted_messages:
        window_idx = int(timestamp // window_size)
        if window_idx < num_windows:
            window_counts[window_idx] += weight

    # Calculate rolling average (baseline)
    rolling_window = 10
    rolling_avg = np.zeros_like(window_counts)
    for i in range(len(window_counts)):
        start = max(0, i - rolling_window // 2)
        end = min(len(window_counts), i + rolling_window // 2 + 1)
        rolling_avg[i] = np.mean(window_counts[start:end])

    # Identify spikes
    spikes = []
    for i in range(len(window_counts)):
        # Avoid division by zero or very low baseline
        baseline = max(rolling_avg[i], 1.0)
        if window_counts[i] > threshold_factor * baseline:
            # Spike at the middle of the window
            timestamp = float(i * window_size + window_size / 2)
            score = float(window_counts[i] / baseline)
            spikes.append((timestamp, score))
            
    return spikes

def format_timestamp(seconds):
    """Formats seconds into HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def find_segments(audio_peaks, chat_spikes, video_duration, window_size=15, max_duration=90):
    """
    Combines audio and chat signals into interesting segments.
    """
    # Combine signals into a list of events
    signals = []
    for t, s in audio_peaks:
        signals.append({'time': t, 'score': s, 'type': 'audio'})
    for t, s in chat_spikes:
        signals.append({'time': t, 'score': s, 'type': 'chat'})
    
    if not signals:
        return []
        
    # Sort signals by time
    signals.sort(key=lambda x: x['time'])
    
    # Group signals within window_size (15s)
    events = []
    current_event = [signals[0]]
    for i in range(1, len(signals)):
        if signals[i]['time'] - current_event[-1]['time'] <= window_size:
            current_event.append(signals[i])
        else:
            events.append(current_event)
            current_event = [signals[i]]
    events.append(current_event)
    
    # Process events into segments
    segments = []
    for event in events:
        first_signal = event[0]['time']
        last_signal = event[-1]['time']
        
        start = max(0, first_signal - 5)
        end = min(video_duration, last_signal + 10)
        
        # Limit duration
        if end - start > max_duration:
            end = start + max_duration
            
        # Calculate score and reason
        total_score = float(sum(s['score'] for s in event))
        types = set(s['type'] for s in event)
        if 'audio' in types and 'chat' in types:
            reason = "Audio + Chat Spike"
        elif 'audio' in types:
            reason = "Audio Peak"
        else:
            reason = "Chat Spike"
            
        segments.append({
            'start_s': start,
            'end_s': end,
            'start': format_timestamp(start),
            'end': format_timestamp(end),
            'score': total_score,
            'reason': reason
        })
    
    # Ranking: Top 10 per hour
    num_hours = int(video_duration // 3600) + 1
    ranked_segments = []
    
    for h in range(num_hours):
        hour_start = h * 3600
        hour_end = (h + 1) * 3600
        
        hour_segments = [s for s in segments if hour_start <= s['start_s'] < hour_end]
        # Sort by score descending
        hour_segments.sort(key=lambda x: x['score'], reverse=True)
        # Take top 10
        ranked_segments.extend(hour_segments[:10])
        
    # Final sort by time
    ranked_segments.sort(key=lambda x: x['start_s'])
    
    # Remove internal fields for output
    for s in ranked_segments:
        s.pop('start_s', None)
        s.pop('end_s', None)
        
    return ranked_segments

def analyze_video(video_path, chat_json=None, threshold_audio=2.0, threshold_chat=1.5):
    """
    Full analysis pipeline: extract signals, fuse them, and save segments.json.
    """
    if not os.path.exists(video_path):
        print(f"Error: Video file {video_path} not found.")
        return []
        
    # Get video duration using ffprobe
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        duration_output = subprocess.check_output(cmd).decode().strip()
        video_duration = float(duration_output)
    except Exception as e:
        print(f"Error getting video duration: {e}")
        video_duration = 3600 # Fallback
        
    print(f"Analyzing {video_path} (Duration: {format_timestamp(video_duration)})...")
    
    print("Extracting audio peaks...")
    audio_peaks = extract_audio_peaks(video_path, threshold_factor=threshold_audio)
    
    chat_spikes = []
    if chat_json and os.path.exists(chat_json):
        print(f"Analyzing chat from {chat_json}...")
        chat_spikes = analyze_chat_velocity(chat_json, threshold_factor=threshold_chat)
    elif chat_json:
        print(f"Warning: Chat JSON {chat_json} not found.")
        
    print("Fusing signals and finding segments...")
    segments = find_segments(audio_peaks, chat_spikes, video_duration)
    
    output_path = os.path.join(os.path.dirname(os.path.abspath(video_path)), "segments.json")
    with open(output_path, "w") as f:
        json.dump(segments, f, indent=2)
        
    print(f"Found {len(segments)} segments. Saved to {output_path}")
    return segments

if __name__ == "__main__":
    # Test script for standalone use
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze video and chat to find interesting segments.")
    parser.add_argument("video_path", help="Path to the video file")
    parser.add_argument("--chat_json", help="Path to the chat JSON file (rechat format)")
    parser.add_argument("--threshold_audio", type=float, default=2.0, help="Audio peak threshold factor")
    parser.add_argument("--threshold_chat", type=float, default=1.5, help="Chat spike threshold factor")
    
    args = parser.parse_args()
    
    analyze_video(args.video_path, args.chat_json, args.threshold_audio, args.threshold_chat)
