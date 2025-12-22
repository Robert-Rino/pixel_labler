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

def transcribe_video(
    input_file: str,
    output_file: str = "zh.srt",
    model_size: str = "medium",
    device: str = "auto",
    compute_type: str = "int8",
    translate_to_zh: bool = True,
    translation_engine: str = "ollama",
    ollama_model: str = "hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF"
):
    """
    Core function to transcribe and optionally translate a video file.
    
    Args:
        input_file: Path to the input video/audio file.
        output_file: Path to save the SRT file (default: "zh.srt").
        model_size: Whisper model size (default: "medium").
        device: "cuda", "cpu", or "auto" (default: "auto").
        compute_type: "int8" or "float16" (default: "int8").
        translate_to_zh: Whether to translate English to Chinese (default: True).
        translation_engine: "ollama" or "argostranslate" (default: "ollama").
        ollama_model: Ollama model to use (default: Llama-3-Taiwan...).
    """
    input_path = os.path.abspath(input_file)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
        
    # Resolve output file path
    # If output_file is just a filename (no directory), save it in the same folder as input_file
    if not os.path.isabs(output_file) and os.path.dirname(output_file) == "":
        output_file = os.path.join(os.path.dirname(input_path), output_file)

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
        initial_prompt="以下是繁體中文的字幕。"
    )

    print(f"Detected language '{info.language}' with probability {info.language_probability:.2f}")

    # Prepare Translation if needed
    need_translate = False
    converter = None
    
    if info.language == "en" and translate_to_zh:
        need_translate = True
        
        if translation_engine == "ollama":
            print(f"Language is English. Using Ollama ({ollama_model}) for translation...")
            try:
                requests.get("http://localhost:11434")
                print("Ollama connection established.")
            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to Ollama. Make sure 'ollama serve' is running.")
                return # Should this raise?
                
        elif translation_engine == "argostranslate":
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

    print(f"Writing subtitle to: {output_file}")
    
    with open(output_file, "w", encoding="utf-8") as f:
        count = 1
        for segment in segments:
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            text = segment.text.strip()
            print(f'transcripted text: {text}')
            
            if need_translate:
                if translation_engine == "ollama":
                    translated = translate_with_ollama(text, model=ollama_model)
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

def main():
    parser = argparse.ArgumentParser(description="Local Whisper Transcription Tool")
    parser.add_argument("input_file", help="Path to input video/audio file")
    parser.add_argument("--model_size", default="medium", help="Whisper model size (small, medium, large-v3)")
    parser.add_argument("--device", default="auto", help="cuda or cpu (auto detects)")
    parser.add_argument("--compute_type", default="int8", help="int8 or float16")
    parser.add_argument("--translate_to_zh", type=str_to_bool, default=True, help="Whether to translate English to Chinese")
    parser.add_argument("--translation_engine", default="ollama", choices=["ollama", "argostranslate"], help="Translation engine to use")
    parser.add_argument("--ollama_model", default="hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF", help="Ollama model to use for translation")
    parser.add_argument("--output", default="zh.srt", help="Output SRT filename (default: zh.srt)")

    args = parser.parse_args()

    try:
        transcribe_video(
            input_file=args.input_file,
            output_file=args.output,
            model_size=args.model_size,
            device=args.device,
            compute_type=args.compute_type,
            translate_to_zh=args.translate_to_zh,
            translation_engine=args.translation_engine,
            ollama_model=args.ollama_model
        )
    except Exception as e:
        print(f"Error during transcription: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()