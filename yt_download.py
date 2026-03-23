import os
import sys
import argparse
import re
import yt_dlp
import subprocess
from transcript import transcribe_video
from typing import Optional, Dict

def clean_filename(text: str) -> str:
    """Remove invalid characters for folder names."""
    return re.sub(r'[\\/*?:"<>|]', "", text).strip()

def validate_youtube_url(url: str) -> bool:
    """Simple validation for YouTube URLs."""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})|'
        r'(https?://)?(www\.)?youtube\.com/shorts/([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url) is not None

def _extract_audio(input_video: str, output_audio: str, use_copy: bool = False):
    """Helper to extract audio from video using FFmpeg."""
    if os.path.exists(output_audio):
        return
    
    print(f"Extracting audio to {output_audio}...")
    cmd = ["ffmpeg", "-y", "-i", input_video, "-vn"]
    if use_copy:
        cmd += ["-c:a", "copy"]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Audio extraction failed: {e}")

def _download_chunked(url: str, output_dir: str, duration: int, extract_audio: bool):
    """Downloads video in 1-hour chunks."""
    for i, start_sec in enumerate(range(0, int(duration), 3600)):
        end_sec = min(start_sec + 3600, duration)
        chunk_name = f"{start_sec//60}-{int(end_sec//60)}"
        chunk_dir = os.path.join(output_dir, chunk_name)
        
        if not os.path.exists(chunk_dir):
            os.makedirs(chunk_dir)
             
        print(f"--> Processing Chunk {i+1}: {chunk_name} ({start_sec}-{end_sec}s)")
        chunk_output = os.path.join(chunk_dir, "original.mp4")
        
        if not os.path.exists(chunk_output):
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': chunk_output,
                'merge_output_format': 'mp4',
                'download_ranges': lambda _, _2, s=start_sec, e=end_sec: [{'start_time': s, 'end_time': e}],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        if extract_audio:
            _extract_audio(chunk_output, os.path.join(chunk_dir, "audio.wav"))

def download_video(url: str, root_dir: str = ".", force_transcript: bool = False, extract_audio: bool = True):
    if not validate_youtube_url(url):
        print(f"Error: Invalid YouTube URL: {url}")
        sys.exit(1)

    # 1. Get Metadata
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            title = info.get('title', 'Untitled')
            description = info.get('description', '')
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        sys.exit(1)

    output_dir = os.path.join(os.path.abspath(root_dir), clean_filename(title)[:240])
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 2. Chunked Download for long videos
    if duration > 3600:
        print(f"Long video ({duration}s). Switching to chunked download.")
        _download_chunked(url, output_dir, duration, extract_audio)
        return

    # 3. Standard Download
    video_output = os.path.join(output_dir, "original.mp4")
    print(f"Downloading: {title}")
    with yt_dlp.YoutubeDL({
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': video_output,
        'merge_output_format': 'mp4',
    }) as ydl:
        ydl.download([url])

    # 4. Post-processing
    with open(os.path.join(output_dir, "metadata.md"), "w", encoding="utf-8") as f:
        f.write(f"```\nSource: {url}\nTitle: {title}\nDescription: {description}\n```\n")

    if extract_audio or force_transcript:
        _extract_audio(video_output, os.path.join(output_dir, "audio.mp4"), use_copy=True)

    # 5. Transcription
    is_short = "/shorts/" in url or (0 < duration < 180)
    if is_short or force_transcript:
        print(f"\nAuto-transcribing...")
        transcribe_video(input_file=video_output, output_file=os.path.join(output_dir, "transcript.srt"), google_translate=True)

def main():
    parser = argparse.ArgumentParser(description="YouTube Downloader")
    parser.add_argument("url", help="YouTube Video URL")
    parser.add_argument("--root_dir", default=".", help="Root directory")
    parser.add_argument("--transcript", action="store_true", help="Force transcript")
    parser.add_argument("--audio", action=argparse.BooleanOptionalAction, default=True, help="Extract audio")
    args = parser.parse_args()

    download_video(args.url, root_dir=args.root_dir, force_transcript=args.transcript, extract_audio=args.audio)

if __name__ == "__main__":
    main()
