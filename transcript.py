import os
import sys
import argparse
import time
import requests
import json
import opencc
from datetime import timedelta
from collections import defaultdict
from faster_whisper import WhisperModel
import assemblyai as aai
import srt
from googlecloud import GoogleTranslator

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

def translate_with_google(text, target="zh-TW"):
    """Translate text using Google Translate via deep-translator"""
    try:
        # Re-instantiating might be slow if loop, but acceptable for this script scale.
        # Ideally we'd reuse the translator instance.
        # But deep_translator is stateless mostly or lightweight.
        # Let's check `translate_batch` if needed later.
        return GoogleTranslator(source='auto', target=target).translate(text)
    except Exception as e:
        print(f"Google Translation Error: {e}")
        return text


def translate_srt_zh(
    original_output, 
    zh_output, 
    ollama_model: str = "hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF",
    translation_engine: str = "google"
):
    print(f"Translation enabled ({translation_engine})...")
    
    if translation_engine == "ollama":
        try:
            requests.get("http://localhost:11434")
            print("Ollama connection established.")
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to Ollama. Make sure 'ollama serve' is running.")
            return

    with open(original_output, "r", encoding="utf-8") as f_orig:
        srt_parsed = srt.parse(f_orig.read() )

    with open(zh_output, "w", encoding="utf-8") as zh_file:
        for line in srt_parsed:
                if translation_engine == "google":
                    translated = translate_with_google(line.content, target="zh-TW")
                else:
                    translated = translate_with_ollama(line.content, model=ollama_model)
                
                line.content = translated
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
    output_file: str,
    model_size: str = "medium",
    device: str = "auto",
    compute_type: str = "int8",
    engine: str = "assemblyai"
    speaker_labels: bool = False,
):
    """
    Core function to transcribe and optionally translate a video file.
    
    Args:
        input_file: Path to the input video/audio file.
        model_size: Whisper model size (default: "medium").
        device: "cuda", "cpu", or "auto" (default: "auto").
        compute_type: "int8" or "float16" (default: "int8").
        ollama_model: Ollama model to use (default: Llama-3-Taiwan...).
        engine: "assemblyai" or "faster_whisper" (default: "assemblyai").
    """
    segments = []
    
    if engine == "assemblyai":
        api_key = os.environ.get("ASSEMBLYAI_API_KEY")
        if not api_key:
            print("Error: ASSEMBLYAI_API_KEY environment variable not set.")
            sys.exit(1)
            
        aai.settings.api_key = api_key
        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(
            # speaker_labels=True,
            format_text=True,
            punctuate=True,
            language_detection=True,
            disfluencies=True,
        )

        if speaker_labels:
            config.speaker_labels = True
            config.speech_understanding={
                "request": {
                    "translation": {
                        "target_languages": ["zh"],
                        "formal": False,
                        "match_original_utterance": True
                    }
                }
            }
        
        print(f"Starting Analysis & Transcription (AssemblyAI)...")
        transcript = transcriber.transcribe(input_file, config=config)
        
        if transcript.status == aai.TranscriptStatus.error:
            print(f"AssemblyAI Error: {transcript.error}")
            sys.exit(1)
        
        # 1. Export Full SRT
        srt_result = transcript.export_subtitles_srt(
            # Optional: Customize the maximum number of characters per caption
            chars_per_caption=32
        )

        print(f"Writing original transcript to: {output_file}")
        with open(output_file, "w", encoding="utf-8") as f_orig:
          f_orig.write(srt_result)
          
        if not speaker_labels:
          return
        
        # 2. Export per-speaker SRTs
        # Group utterances by speaker
        by_speaker = defaultdict(list)
        
        def ms_to_srt_time(ms: int) -> str:
            h = ms // 3600000
            m = (ms % 3600000) // 60000
            s = (ms % 60000) // 1000
            ms_rem = ms % 1000
            return f"{h:02}:{m:02}:{s:02},{ms_rem:03}"

        for i, u in enumerate(transcript.utterances, start=1):
            by_speaker[u.speaker].append(u)

        # Write one SRT file per speaker
        base_dir = os.path.dirname(output_file)
        transcript_dir = os.path.join(base_dir, "transcript")
        if not os.path.exists(transcript_dir):
            os.makedirs(transcript_dir)
            
        print(f"Processing {len(by_speaker)} speakers...")
            
        for speaker, uts in by_speaker.items():
            lines = []
            lines_zh = []
            for i, u in enumerate(uts, start=1):
                # Original
                lines.append(str(i))
                lines.append(f"{ms_to_srt_time(u.start)} --> {ms_to_srt_time(u.end)}")
                lines.append(u.text)
                lines.append("") # Blank line
                
                # Translated
                zh_text = getattr(u, "translated_texts", {}).get("zh")
                if zh_text:
                    lines_zh.append(str(i))
                    lines_zh.append(f"{ms_to_srt_time(u.start)} --> {ms_to_srt_time(u.end)}")
                    lines_zh.append(zh_text)
                    lines_zh.append("") 
            
            # Write Original
            fname = os.path.join(transcript_dir, f"speaker_{speaker}.srt")
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print("Wrote", fname)
            
            # Write Translated (Convert to Traditional Chinese)
            if lines_zh:
                converter = opencc.OpenCC('s2t.json')
                fname_zh = os.path.join(transcript_dir, f"speaker_{speaker}_zh.srt")
                with open(fname_zh, "w", encoding="utf-8") as f:
                    f.write("\n".join(converter.convert(lines_zh)))
                print("Wrote", fname_zh)

        
    else:
        # Default: faster_whisper
        # 1. Setup Device
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"Loading Whisper Model: {model_size} on {device} ({compute_type})...")
        
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        print("Starting Analysis & Transcription (faster-whisper)...")
        
        segments_gen, info = model.transcribe(
            input_file, 
            vad_filter=True,
        )

        # info is returned immediately by faster-whisper
        info_language = info.language
        print(f"Detected language '{info_language}' with probability {info.language_probability:.2f}")
        segments = segments_gen

        print(f"Writing original transcript to: {output_file}")
        
        # Open files
        with open(output_file, "w", encoding="utf-8") as f_orig:
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


def main():
    parser = argparse.ArgumentParser(description="Local Whisper Transcription Tool")
    parser.add_argument("input_file", help="Path to input video/audio file")
    parser.add_argument("--zh_output", default=None, help="Output path for translated Chinese subtitle (optional)")
    parser.add_argument("--split-by-hour", action="store_true", help="Splitting transcript by hour")
    parser.add_argument("--engine", default="assemblyai", choices=["assemblyai", "faster_whisper"], help="Transcription engine to use")
    parser.add_argument("--translation_engine", default="google", choices=["google", "ollama"], help="Translation engine to use (default: google)")

    args = parser.parse_args()
    input_file = os.path.abspath(args.input_file)

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")
        
    # Resolve output file paths
    # Original transcript always goes to transcript.srt in the same directory as input
    original_output = os.path.join(os.path.dirname(input_file), "transcript.srt")
    try:
        transcribe_video(
            input_file=input_file,
            output_file=original_output,
            engine=args.engine
        )
    except Exception as e:
        print(f"Error during transcription: {e}")
        sys.exit(1)

    if args.split_by_hour:
        split_srt_by_hour(original_output)

    # Resolve zh_output if provided
    if args.zh_output:
        if not os.path.isabs(args.zh_output) and os.path.dirname(args.zh_output) == "":
            zh_output = os.path.join(os.path.dirname(input_file), args.zh_output)

        translate_srt_zh(
            original_output, 
            zh_output=zh_output, 
            ollama_model=args.ollama_model,
            translation_engine=args.translation_engine
        )


if __name__ == "__main__":
    main()