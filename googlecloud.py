import argparse
import sys
import os
import re
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

    @classmethod
    def remove_mandarin_punctuation(cls, text: str) -> str:
        """
        Removes Chinese/CJK punctuation and standard ASCII punctuation.
        """
        # 1. \u3000-\u303f : CJK Symbols and Punctuation (e.g., 、 。 〉)
        # 2. \uff00-\uffef : Full-width ASCII variants (e.g., ， ？ ！ ：)
        # 3. Standard ASCII punctuation (optional, added for safety)
        
        # Define the regex pattern for all punctuation
        punctuation_pattern = r"[\u3000-\u303f\uff00-\uffef!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~]+"
        
        return re.sub(punctuation_pattern, "", text)

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
        Uses <s> tags to separate lines.
        """
        output_file = os.path.join(os.path.dirname(input_file), output_file)
            
        print(f"Translating {input_file} -> {output_file} ({self.target})...")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        try:
            subs = list(srt.parse(content))
        except srt.SRTParseError as e:
            print(f"Error parsing SRT file: {e}", file=sys.stderr)
            return

        texts = [sub.content.replace('\n', ' ') for sub in subs] 
        
        # Build chunks based on character limit
        chunks = []
        current_chunk = []
        current_len = 0
        MAX_CHARS = 4500 # Safety margin
        
        for t in texts:
            # Estimate length with tags "<s>" + t + "</s>"
            # Tag length: 3 + 4 = 7
            item_len = len(t) + 7 
            
            if current_len + item_len > MAX_CHARS:
                 chunks.append(current_chunk)
                 current_chunk = []
                 current_len = 0
            
            current_chunk.append(t)
            current_len += item_len
            
        if current_chunk:
            chunks.append(current_chunk)
            
        translated_texts = []
        
        print(f"Processing {len(texts)} lines in {len(chunks)} context blocks...")
        
        import re

        for i, chunk in enumerate(chunks):
            # Wrap each line with <s>...</s>
            tagged_chunk = ["<s>" + t + "</s>" for t in chunk]
            joined_text = "".join(tagged_chunk)
            
            try:
                # Translate
                trans_result = self.translate(joined_text)
                
                # Parse results: Extract content between <s> and </s>
                # Note: Google Translate might mess up tags slightly, e.g. <S> or </ s> or adding spaces.
                # Regex needs to be robust.
                # Common variations: <s>, < s>, < S>, </s>, < /s>, etc.
                matches = re.findall(r'<s>(.*?)</s>', trans_result, re.IGNORECASE | re.DOTALL)
                
                # Fallback check
                if len(matches) != len(chunk):
                    print(f"Warning: Chunk {i} alignment mismatch! Input: {len(chunk)}, Output: {len(matches)}")
                    # Fallback to individual translation for this chunk
                    print("Fallback to individual translation for this chunk...")
                    
                    fallback_res = []
                    if len(chunk) > 0:
                        try:
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
                    translated_texts.extend([self.remove_mandarin_punctuation(m).strip() for m in matches])
                    
                print(f"Translated chunk {i+1}/{len(chunks)}...", end='\r')
                
            except Exception as e:
                print(f"Chunk translation failed: {e}", file=sys.stderr)
                translated_texts.extend([""] * len(chunk))
        
        print(f"\nTranslation done. Writing to {output_file}")
        
        if len(translated_texts) != len(subs):
             print(f"CRITICAL ERROR: Total output lines {len(translated_texts)} != input {len(subs)}")

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
