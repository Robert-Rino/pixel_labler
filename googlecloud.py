import argparse
import sys
from deep_translator import GoogleTranslator as DeepGoogleTranslator

class GoogleTranslator:
    """
    A nice interface for Google Translate.
    """
    def __init__(self, source='auto', target='zh-TW'):
        self.source = source
        self.target = target
        self.translator = DeepGoogleTranslator(source=self.source, target=self.target)

    def translate(self, text: str, target: str = None) -> str:
        """
        Translate text to the target language.
        
        Args:
            text (str): The text to translate.
            target (str, optional): Target language code (e.g. 'zh-TW', 'en'). 
                                    Defaults to the instance's target.
        
        Returns:
            str: The translated text.
        """
        if not text:
            return ""
            
        # Re-initialize if target changes
        if target and target != self.target:
            self.target = target
            self.translator = DeepGoogleTranslator(source=self.source, target=self.target)
            
        try:
            return self.translator.translate(text)
        except Exception as e:
            print(f"Translation failed: {e}", file=sys.stderr)
            return text

def main():
    parser = argparse.ArgumentParser(description="Google Translate CLI")
    parser.add_argument("text", help="Text to translate (or file path)")
    parser.add_argument("-t", "--target", default="zh-TW", help="Target language code (default: zh-TW)")
    parser.add_argument("-s", "--source", default="auto", help="Source language code (default: auto)")
    
    args = parser.parse_args()
    
    # Check if text is a file path
    text_to_translate = args.text
    import os
    if os.path.exists(args.text) and os.path.isfile(args.text):
        try:
            with open(args.text, 'r', encoding='utf-8') as f:
                text_to_translate = f.read()
        except:
            pass # Treat as raw text if read fails

    translator = GoogleTranslator(source=args.source, target=args.target)
    result = translator.translate(text_to_translate)
    print(result)

if __name__ == "__main__":
    main()
