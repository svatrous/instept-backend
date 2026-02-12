from google import genai
from google.genai import types
import os
import time
import json
from models import Recipe
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

client = genai.Client(api_key=api_key)

def analyze_video(video_path: str) -> Recipe:
    """
    Uploads a video to Gemini and analyzes it to extract a recipe.
    """
    print(f"Uploading file: {video_path}")
    # Upload the file
    video_file = client.files.upload(file=video_path)
    print(f"Completed upload: {video_file.name}")

    # Wait for processing
    while video_file.state == "PROCESSING":
        print('.', end='', flush=True)
        time.sleep(10)
        video_file = client.files.get(name=video_file.name)

    if video_file.state == "FAILED":
        raise ValueError("Video processing failed.")

    print(f"\nFile is ready: {video_file.name}")

    prompt = """
    Проанализируй это видео и извлеки рецепт.
    Верни результат в формате JSON следующей структуры:
    {
        "title": "Название рецепта",
        "description": "Краткое описание",
        "ingredients": [
            {"name": "Название ингредиента", "amount": "Количество", "unit": "Единица измерения"}
        ],
        "steps": [
            "Шаг 1",
            "Шаг 2"
        ]
    }
    Убедись, что выходные данные являются валидным JSON. Не включай блоки кода markdown.
    """

    try:
        # Generate content
        response = client.models.generate_content(
            model="gemini-3.0-flash",
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # Simple cleanup of potential markdown code blocks
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(text_response)
        return Recipe(**data)
        
    except Exception as e:
        print(f"Error during generation: {e}")
        raise ValueError(f"Gemini generation failed: {e}")
        
    finally:
        # Cleanup remote file requires name?
        # The new SDK might handle cleanup differently or require explicit call.
        # client.files.delete(name=video_file.name)
        try:
             client.files.delete(name=video_file.name)
        except Exception:
             pass

