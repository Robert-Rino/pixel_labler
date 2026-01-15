import argparse
import sys
import os
from google.cloud import translate_v2 as translate

import srt

class GoogleTranslator:
    """
    A wrapper for Google Cloud Translation API (Basic / v2).
    Requires GOOGLE_APPLICATION_CREDENTIALS environment variable.
    """
    def __init__(self, source='auto', target='zh-TW'):
        self.source = source
        self.target = target
        try:
            self.client = translate.Client()
        except Exception as e:
            print(f"Failed to initialize Google Translate Client: {e}", file=sys.stderr)
            self.client = None

    def translate(self, text: str, target: str = None) -> str:
        """
        Translate text to the target language.
        """
        if not text:
            return ""
            
        if self.client is None:
            print("Google Translate Client not initialized.", file=sys.stderr)
            return text

        # Use runtime target if provided, else default
        target_lang = target if target else self.target
        
        try:
            # result is typically: {'input': 'text', 'translatedText': '...', 'detectedSourceLanguage': 'en'}
            result = self.client.translate(
                text, 
                target_language=target_lang,
                source_language=self.source if self.source != 'auto' else None
            )
            # Unescape HTML entities if needed? V2 API usually returns HTML-encoded text.
            # E.g. &#39; -> '
            import html
            return html.unescape(result['translatedText'])
        except Exception as e:
            print(f"Translation failed: {e}", file=sys.stderr)
            return text
            
    def translate_file(self, input_file: str, output_file: str = 'zh.srt'):
        """
        Translate an SRT file with context awareness (joining lines).
        """
        # If output_file is provided (or default) but has no directory component,
        # save it in the same directory as the input file.
        output_file = os.path.join(os.path.dirname(input_file), output_file)
            
        print(f"Translating {input_file} -> {output_file} ({self.target})...")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
            trans_result = self.translate(content)
            
        try:
            subs = list(srt.parse(content))
        except srt.SRTParseError as e:
            print(f"Error parsing SRT file: {e}", file=sys.stderr)
            return
        # Context-Aware Translation:
        # Join all keys into a single text (or large blocks).
        # We use a special delimiter or just newlines? Newlines are safer for NMT.
        # However, Google Translate might merge lines.
        # Safe strategy: Chunk by ~2000-5000 chars to avoid timeout/limits but provide context.
        # Use <br> or just \n. \n is standard for text/plain.
        
        texts = [sub.content.replace('\n', ' ') for sub in subs] # Handle multiline subs? Flatten them first.
        # Actually subtitle lines can be multiline. But usually better to treating entire subtitle as one sentence?
        # Let's keep original newlines? or Replace them?
        # Ideally: sub 1 context \n sub 2 context.
        
        # We will iterate and build chunks.
        chunks = []
        current_chunk = []
        current_len = 0
        MAX_CHARS = 4500 # Safety margin under 5000? v2 limit? v2 POST limit ~100k?
        # Let's try 4000 chars.
        
        for t in texts:
            # Flatten internal newlines of a single subtitle to avoid confusing the splitter?
            # Or keep them? If we keep them, splitting back by \n is hard if we don't know how many lines.
            # Compromise: Replace internal newlines with space for context translation?
            # Usually subtitles are short.
            t_flat = t.replace('\n', ' ')
            if current_len + len(t_flat) + 1 > MAX_CHARS:
                 chunks.append(current_chunk)
                 current_chunk = []
                 current_len = 0
            
            current_chunk.append(t_flat)
            current_len += len(t_flat) + 1
            
        if current_chunk:
            chunks.append(current_chunk)
            
        translated_texts = []
        
        print(f"Processing {len(texts)} lines in {len(chunks)} context blocks...")
        
        for i, chunk in enumerate(chunks):
            # Join with newline
            joined_text = "\n".join(chunk)
            
            try:
                # Translate as one big text
                # We expect result to have same number of lines
                trans_result = self.translate(joined_text)
                
                # Split back
                splitted = trans_result.split('\n')
                
                # Verify alignment
                if len(splitted) != len(chunk):
                    print(f"Warning: Chunk {i} alignment mismatch! Input: {len(chunk)}, Output: {len(splitted)}")
                    # Try to heal? 
                    # If output has fewer lines, maybe merged?
                    # If more, maybe split?
                    # Fallback: If mismatch, translate individually for this chunk (losing context but safe)
                    print("Fallback to line-by-line for this chunk due to mismatch.")
                    fallback_res = []
                    # Doing naive line-by-line fallback
                    # This is slow but safe.
                    # Batch request for fallback
                    if len(chunk) > 0:
                        try:
                           # Use client.translate list support
                           batch_res = self.client.translate(
                                chunk,
                                target_language=self.target,
                                source_language=self.source if self.source != 'auto' else None
                           )
                           if isinstance(batch_res, dict): batch_res = [batch_res]
                           import html
                           fallback_res = [html.unescape(r['translatedText']) for r in batch_res]
                        except Exception as e:
                            print(f"Fallback failed: {e}")
                            fallback_res = [""] * len(chunk)
                    
                    translated_texts.extend(fallback_res)
                else:
                    # Clean up
                    translated_texts.extend([s.strip() for s in splitted])
                    
                print(f"Translated chunk {i+1}/{len(chunks)}...", end='\r')
                
            except Exception as e:
                print(f"Chunk translation failed: {e}", file=sys.stderr)
                translated_texts.extend([""] * len(chunk))
        
        print(f"\nTranslation done. Writing to {output_file}")
        
        # Reassemble
        # Handle length mismatch if total differs? (Should happen only if logic bug)
        if len(translated_texts) != len(subs):
             print(f"CRITICAL ERROR: Total output lines {len(translated_texts)} != input {len(subs)}")
             # Should not happen due to fallback logic above ensuring len match per chunk
        
        for sub, trans in zip(subs, translated_texts):
            sub.content = trans
            
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(srt.compose(subs))

def main():
    parser = argparse.ArgumentParser(description="Google Cloud Translate CLI")
    parser.add_argument("text", help="Text to translate OR path to .srt file")
    parser.add_argument("-t", "--target", default="zh-TW", help="Target language code (default: zh-TW)")
    parser.add_argument("-s", "--source", default="auto", help="Source language code (default: auto)")
    # parser.add_argument("-o", "--output", help="Output file path (for file translation)")
    
    args = parser.parse_args()
    
    translator = GoogleTranslator(source=args.source, target=args.target)

    # Check if input is a file
    if os.path.exists(args.text) and os.path.isfile(args.text):
        if args.text.lower().endswith('.srt'):
            translator.translate_file(args.text)
            return
        else:
             # Regular text file?
            try:
                with open(args.text, 'r', encoding='utf-8') as f:
                    text_to_translate = f.read()
                    print(translator.translate(text_to_translate))
                    return
            except:
                pass
    
    # Treat as raw string
    result = translator.translate(args.text)
    print(result)

if __name__ == "__main__":
    main()
