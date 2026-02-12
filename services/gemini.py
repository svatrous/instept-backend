import google.generativeai as genai
import os
import time
import json
from ..models import Recipe
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=api_key)

def analyze_video(video_path: str) -> Recipe:
    """
    Uploads a video to Gemini and analyzes it to extract a recipe.
    """
    print(f"Uploading file: {video_path}")
    video_file = genai.upload_file(path=video_path)
    print(f"Completed upload: {video_file.uri}")

    while video_file.state.name == "PROCESSING":
        print('.', end='', flush=True)
        time.sleep(10)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
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

    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    # request JSON response for stability
    response = model.generate_content(
        [video_file, prompt],
        generation_config={"response_mime_type": "application/json"}
    )
    
    # Simple cleanup of potential markdown code blocks (Gemini might still add them in JSON mode sometimes)
    text_response = response.text.replace("```json", "").replace("```", "").strip()
    
    try:
        data = json.loads(text_response)
        return Recipe(**data)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON: {text_response}")
        raise ValueError("Failed to parse Gemini response as JSON")
    finally:
        # Cleanup remote file
        genai.delete_file(video_file.name)
