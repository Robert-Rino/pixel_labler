import os
import sys
import argparse
import time
import requests
import json
from datetime import timedelta
from faster_whisper import WhisperModel

def str_to_bool(value):
    if isinstance(value, bool):
        return value
    if value.lower() in {'false', 'f', '0', 'no', 'n'}:
        return False
    return True

def format_timestamp(seconds: float, always_include_hours: bool = False, decimal_marker: str = ',') -> str:
    """Standard SRT timestamp format: HH:MM:SS,mmm"""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)

    hours = milliseconds // 3600000
    milliseconds -= hours * 3600000

    minutes = milliseconds // 60000
    milliseconds -= minutes * 60000

    seconds = milliseconds // 1000
    milliseconds -= seconds * 1000

    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else "00:"
    return f"{hours_marker}{minutes:02d}:{seconds:02d}{decimal_marker}{milliseconds:03d}"

def write_srt(transcript, file):
    """Write lines to file in SRT format"""
    for i, segment in enumerate(transcript, start=1):
        print(f"{i}\n"
              f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n"
              f"{segment.text.strip().replace('-->', '->')}\n", file=file, flush=True)

def translate_with_ollama(text, model="llama3"):
    """Translate text using local Ollama API"""
    url = "http://localhost:11434/api/generate"
    
    prompt = f"""You are a professional subtitle translator. Translate the following English text to Traditional Chinese (Taiwan style).
    Output ONLY the translated text, no explanations, no notes.
    
    Text: "{text}"
    Translation:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "").strip().strip('"').strip("'")
    except requests.exceptions.RequestException as e:
        print(f"Ollama Translation Error: {e}")
        return text # Return original text on error


def translate_srt_zh(
    original_output, 
    zh_output, 
    ollama_model: str = "hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF",
):
    print(f"Translation enabled (Ollama: {ollama_model})...")
    try:
        requests.get("http://localhost:11434")
        print("Ollama connection established.")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Ollama. Make sure 'ollama serve' is running.")

    with open(original_output, "r", encoding="utf-8") as f_orig:
        srt_parsed = srt.parse(f_orig.read() )

    with open(zh_output, "w", encoding="utf-8") as zh_file:
        for line in srt_parsed:
                translated = translate_with_ollama(line.content, model=ollama_model)
                zh_file.write(line.to_srt())
                zh_file.flush()

    print(f"Translation completed")
    



def split_srt_by_hour(input_srt):
    """
    Split a large SRT file into multiple files based on hour.
    transcript.srt -> transcript-0.srt (0h-1h), transcript-1.srt (1h-2h), etc.
    """
    if not os.path.exists(input_srt):
        return

    print(f"Splitting SRT by hour: {input_srt}")
    
    base_name = os.path.dirname(input_srt) # e.g. /path/to/transcript
    # We want transcript-0.srt
    
    current_hour = -1
    current_file = None
    
    count = 1
    
    with open(input_srt, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line: # Skip empty lines/separators
            i += 1
            continue
            
        # SRT block structure:
        # Index
        # Timestamp --> Timestamp
        # Text
        # (Blank line)
        
        # Check if line looks like index
        if line.isdigit():
            index = line
            if i + 1 >= len(lines): break
            timestamp_line = lines[i+1].strip()
            
            if '-->' in timestamp_line:
                start_str, end_str = timestamp_line.split(' --> ')
                start_str = start_str.strip()
                
                # Determine hour
                # simple parsing HH:MM:SS,mmm
                try:
                    h_str = start_str.split(':')[0]
                    hour = int(h_str)
                except:
                    hour = 0
                
                if hour != current_hour:
                    if current_file:
                        current_file.close()
                    
                    current_hour = hour
                    
                    # Output to {base_name}/transcript-chunked/
                    output_dir = os.path.join(base_name, "transcript-chunked")
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    
                    # Filename: transcript-0.srt inside the folder
                    # Use os.path.basename(base_name) to get "transcript"
                    filename_only = f"{os.path.basename(base_name)}-{current_hour}.srt"
                    output_filename = os.path.join(output_dir, filename_only)
                    
                    print(f"Creating hourly split: {output_filename}")
                    current_file = open(output_filename, 'w', encoding='utf-8')
                    # Reset counter for new file? Usually valid SRTs start at 1.
                    # But if we split, maybe keeping global index is ok, or reset?
                    # User request: "generate multiple... from transcript.srt".
                    # Usually better to keep sequential index OR reset if it's a standalone view.
                    # I will KEEP original index for now as it maps to original video time.
                    # Wait, usually split SRTs are used for corresponding split video chunks.
                    # But here we are splitting ONLY the SRT. The video is likely still full length?
                    # "transcript-{i}.srt... for each i stands for number i's hour content".
                    # Timestamp should probably be preserved (absolute time), so index implies order.
                
                # Write the block to current file
                if current_file:
                    # Find end of block (empty line)
                    current_file.write(f"{line}\n") # Index
                    current_file.write(f"{timestamp_line}\n") # Time
                    
                    # Read text lines until empty line
                    j = i + 2
                    while j < len(lines):
                        txt_line = lines[j].rstrip() # Keep structure but parse empty line check
                        if not txt_line:
                            current_file.write("\n")
                            break
                        current_file.write(f"{txt_line}\n")
                        j += 1
                    
                    # Advance i
                    i = j + 1
                    continue
        
        i += 1

    if current_file:
        current_file.close()

def transcribe_video(
    input_file: str,
    zh_output: str = None,
    model_size: str = "medium",
    device: str = "auto",
    compute_type: str = "int8",
    split_by_hour: bool = True
):
    """
    Core function to transcribe and optionally translate a video file.
    
    Args:
        input_file: Path to the input video/audio file.
        zh_output: Path to save the translated Chinese SRT file (optional).
        model_size: Whisper model size (default: "medium").
        device: "cuda", "cpu", or "auto" (default: "auto").
        compute_type: "int8" or "float16" (default: "int8").
        ollama_model: Ollama model to use (default: Llama-3-Taiwan...).
        split_by_hour: Whether to split the transcript into hourly chunks (default: True).
    """
    input_path = os.path.abspath(input_file)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
        
    # Resolve output file paths
    # Original transcript always goes to transcript.srt in the same directory as input
    original_output = os.path.join(os.path.dirname(input_path), "transcript.srt")

    # Resolve zh_output if provided
    if zh_output:
        if not os.path.isabs(zh_output) and os.path.dirname(zh_output) == "":
            zh_output = os.path.join(os.path.dirname(input_path), zh_output)

    # 1. Setup Device
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(f"Loading Whisper Model: {model_size} on {device} ({compute_type})...")
    
    
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print("Starting Analysis & Transcription...")
    
    segments, info = model.transcribe(
        input_path, 
        vad_filter=True,
    )

    # info is returned immediately by faster-whisper
    info_language = info.language
    print(f"Detected language '{info_language}' with probability {info.language_probability:.2f}")
    print(f"Writing original transcript to: {original_output}")
    
    # Open files
    f_orig = open(original_output, "w", encoding="utf-8")
    
    with open(original_output, "w", encoding="utf-8") as f_orig:
        count = 1
        for segment in segments:
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            text = segment.text.strip()
            
            # Write Original
            print(f"[{start_time} --> {end_time}] {text}")
            f_orig.write(f"{count}\n")
            f_orig.write(f"{start_time} --> {end_time}\n")
            f_orig.write(f"{text}\n\n")
            f_orig.flush()

            count += 1

    print("Done!")
    
    # Split original transcript by hour
    if split_by_hour and os.path.exists(original_output):
         split_srt_by_hour(original_output)

    if zh_output:
        translate_srt_zh(original_output, zh_output=zh_output)


def main():
    parser = argparse.ArgumentParser(description="Local Whisper Transcription Tool")
    parser.add_argument("input_file", help="Path to input video/audio file")
    parser.add_argument("--model_size", default="medium", help="Whisper model size (small, medium, large-v3)")
    parser.add_argument("--device", default="auto", help="cuda or cpu (auto detects)")
    parser.add_argument("--compute_type", default="int8", help="int8 or float16")
    parser.add_argument("--zh_output", default=None, help="Output path for translated Chinese subtitle (optional)")
    parser.add_argument("--split-by-hour", action="store_true", help="Splitting transcript by hour")

    args = parser.parse_args()

    try:
        transcribe_video(
            input_file=args.input_file,
            zh_output=args.zh_output,
            model_size=args.model_size,
            device=args.device,
            compute_type=args.compute_type,
            split_by_hour=args.split_by_hour
        )
    except Exception as e:
        print(f"Error during transcription: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()