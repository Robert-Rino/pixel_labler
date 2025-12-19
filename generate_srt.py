import time
import os
from google import genai
from google.genai import types

# 1. Setup Client
# Ensure your GEMINI_API_KEY is set in your environment variables
client = genai.Client(api_key="API_KEY")

def generate_srt(video_path, output_srt_name="subtitles.srt"):
    print(f"Uploading file: {video_path}...")
    
    # 2. Upload the video to the File API
    # The File API is required for videos larger than 20MB
    video_file = client.files.upload(file=video_path)
    
    # 3. Wait for the video to be processed
    while video_file.state.name == "PROCESSING":
        print(".", end="", flush=True)
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise ValueError("Video processing failed.")

    print("\nVideo processed. Generating SRT...")

    # 4. Prompt the model for SRT format
    prompt = """
    # SRT 字幕專家任務：短影音專用格式輸出

    請根據提供的影片內容（語音與時間軸），生成多語言的 SRT 字幕檔。

    ## 關鍵要求 (Shorts/CapCut 規範)

    1.  **時間軸格式：** 必須嚴格使用 **標準 SRT 格式**，即 `HH:MM:SS,mmm --> HH:MM:SS,mmm`。
        * **毫秒分隔符：** 必須使用**逗號 (`,`)**，絕對不能使用句點 (`.`)。
    2.  **單行限制：** 每一條時間軸（編號後）只能有一行文字，絕對不能換行。
    3.  **字數限制：**
        * 中文字：每行不超過 10-12 字。
        * 英文字：每行不超過 5-6 個單字。
    4.  **語氣：** 翻譯/聽寫需保持道地、口語化，符合影片中的情緒和風格。
    5.  **輸出格式：** 將每種語言的 SRT 內容單獨放入一個 [Code Block] 中。

    ## 必需語言

    1.  **繁體中文 (Traditional Chinese)** - 台灣在地用語，保留網路梗。
    2.  **英文 (English)** - 適合 TikTok/Reels 的口語簡寫 (如 wanna, gonna)。
    3.  **日文 (Japanese)** - 適合 SNS 的口語風格。
    4.  **韓文 (Korean)** - 適合 SNS 的口語風格。
    """

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[video_file, prompt],
        config=types.GenerateContentConfig(
            temperature=0, # Low temperature for more accurate transcription
        )
    )

    # 5. Save to file
    with open(output_srt_name, "w", encoding="utf-8") as f:
        f.write(response.text)
    
    print(f"SRT file saved as: {output_srt_name}")

# Usage
# generate_srt("path/to/your/video.mp4")

if __name__ == "__main__":
    generate_srt("/Users/nino/Downloads/Gura/亞特蘭提斯術語：我看你，但我不想吃你 🍴 #Atlantis #GawrGura #PeopleWatching #Funny/out.mp4")
