import subprocess
import numpy as np
import os

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
            peaks.append(timestamps[i])
            
    return peaks

def analyze_chat_velocity(json_path, window_size=10, threshold_factor=1.5):
    """
    Parses rechat.json and identifies spikes in weighted chat velocity.
    """
    import json
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
            spikes.append(float(i * window_size + window_size / 2))
            
    return spikes

if __name__ == "__main__":
    # Test script for standalone use
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        peaks = extract_audio_peaks(file_path)
        print(f"Peaks found at: {peaks}")
