import os
import sys
import argparse
import time
import requests
import json
from datetime import timedelta
from faster_whisper import WhisperModel
import argostranslate.package
import argostranslate.translate

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

def setup_argostranslate():
    """Check and install en -> zh translation package if needed"""
    print("Checking translation packages...")
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    
    package_to_install = next(
        filter(
            lambda x: x.from_code == "en" and x.to_code == "zh", available_packages
        ), None
    )
    
    if package_to_install:
        if package_to_install not in argostranslate.package.get_installed_packages():
             print(f"Downloading {package_to_install}...")
             argostranslate.package.install_from_path(package_to_install.download())
             print("Translation package installed.")
    else:
        print("Required translation package (en->zh) not found in index.")

def translate_with_argos(text):
    return argostranslate.translate.translate(text, "en", "zh")

def main():
    parser = argparse.ArgumentParser(description="Local Whisper Transcription Tool")
    parser.add_argument("input_file", help="Path to input video/audio file")
    parser.add_argument("--model_size", default="medium", help="Whisper model size (small, medium, large-v3)")
    parser.add_argument("--device", default="auto", help="cuda or cpu (auto detects)")
    parser.add_argument("--compute_type", default="int8", help="int8 or float16")
    parser.add_argument("--translate_to_zh", type=str_to_bool, default=True, help="Whether to translate English to Chinese")
    parser.add_argument("--translation_engine", default="ollama", choices=["ollama", "argostranslate"], help="Translation engine to use")
    parser.add_argument("--ollama_model", default="hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF", help="Ollama model to use for translation")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input_file)
    if not os.path.exists(input_path):
        print(f"Error: File not found: {input_path}")
        return

    # 1. Setup Device
    device = args.device
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    
    print(f"Loading Whisper Model: {args.model_size} on {device} ({args.compute_type})...")
    
    model = WhisperModel(args.model_size, device=device, compute_type=args.compute_type)

    print("Starting Analysis & Transcription...")
    
    segments, info = model.transcribe(
        input_path, 
        vad_filter=True,
        initial_prompt="以下是繁體中文的字幕。"
    )

    print(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")

    # Prepare Translation if needed
    need_translate = False
    converter = None
    
    if info.language == "en" and args.translate_to_zh:
        need_translate = True
        
        if args.translation_engine == "ollama":
            print(f"Language is English. Using Ollama ({args.ollama_model}) for translation...")
            try:
                requests.get("http://localhost:11434")
                print("Ollama connection established.")
            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to Ollama. Make sure 'ollama serve' is running.")
                return
                
        elif args.translation_engine == "argostranslate":
            print("Language is English. Using Argo Translate (en -> zh)...")
            try:
                setup_argostranslate()
                # Check for Traditional Chinese converter
                try:
                    import opencc
                    converter = opencc.OpenCC('s2t')
                except ImportError:
                    print("Warning: 'opencc-python-reimplemented' not found. Translation might be in Simplified Chinese.")
            except Exception as e:
                print(f"Translation setup failed: {e}")
                need_translate = False

    # Output file
    base_name = os.path.splitext(input_path)[0]
    output_srt = f"{base_name}.srt"
    
    print(f"Writing subtitle to: {output_srt}")
    
    with open(output_srt, "w", encoding="utf-8") as f:
        count = 1
        for segment in segments:
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            text = segment.text.strip()
            print(f'transscripted text {text}')
            
            if need_translate:
                if args.translation_engine == "ollama":
                    translated = translate_with_ollama(text, model=args.ollama_model)
                else:
                    # argostranslate
                    translated = translate_with_argos(text)
                    if converter:
                        translated = converter.convert(translated)
                
                if not translated:
                   translated = text 
                text = translated

            print(f"[{start_time} --> {end_time}] {text}")
            
            f.write(f"{count}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")
            count += 1
            
    print("Done!")

if __name__ == "__main__":
    main()