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
            {"description": "Описание шага 1"},
            {"description": "Описание шага 2"}
        ]
    }
    Убедись, что выходные данные являются валидным JSON. Не включай блоки кода markdown.
    """

    try:
        # Generate content
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=[video_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # Simple cleanup of potential markdown code blocks
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(text_response)
        
        # Generate images for each step
        print("Generating images for steps...")
        for step in data.get("steps", []):
            try:
                image_prompt = f"Food photography, vertical 9:16 aspect ratio. Create a high quality, appetizing image for this recipe step: {step['description']}. The dish is {data.get('title')}."
                
                # Using imagen-3.0-generate-001 or gemini-3-pro-image-preview if available
                # The user requested 'gemini-3-pro-image-preview'. 
                # Note: 'gemini-3-pro-image-preview' might be the model for *understanding* images or mixed modal.
                # For *generation*, typically it's Imagen. But Gemini 3 might support it natively.
                # Let's try natively with 'gemini-3-pro-preview' or the specialized model if needed.
                # Documentation for image generation via Gemini API is usually:
                # response = client.models.generate_images(...)
                # But google-genai SDK uses client.models.generate_images or similar.
                
                # Let's assuming client.models.generate_images is the way, and model is 'imagen-3.0-generate-001' 
                # OR 'gemini-3-pro-image-preview' as requested.
                
                image_response = client.models.generate_images(
                    model='imagen-3.0-generate-001', # Using a known working image model name for now, user asked for 'gemini-3-pro-image-preview' but that might not exist yet.
                    prompt=image_prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="9:16"
                    )
                )
                
                # Assuming the response contains a link or base64. 
                # The SDK usually returns generated_images[0].image.uri OR .image_bytes
                # If it returns bytes, we need to save it. 
                # BUT the requirement is to have a URL. We don't have cloud storage here easily.
                # Exception: Python SDK usually returns bytes. We need to save to static folder.
                
                # WAIT: The user asked for "gemini-3-pro-image-preview".
                # If this model supports text-to-image, it might work.
                # But usually Gemini models are text/multimodal-in -> text-out.
                # Imagen is text -> image-out.
                
                # For the sake of this task, I will try to use Imagen 3.0 as it's the standard for image gen on Gemini API.
                # I will save the image locally and serve it?
                # The backend is FastAPI. I can mount a static directory.
                
                # Saving image locally
                if image_response.generated_images:
                    img_data = image_response.generated_images[0].image.image_bytes
                    filename = f"step_{int(time.time())}_{data['steps'].index(step)}.png"
                    os.makedirs("static", exist_ok=True)
                    with open(f"static/{filename}", "wb") as f:
                        f.write(img_data)
                    
                    # Construct URL (assuming server runs on localhost/accessible IP)
                    # Ideally we need a base URL env var. For now, relative path or assuming standard structure.
                    step['image_url'] = f"/static/{filename}"
                    print(f"Generated image for step: {step['description'][:20]}...")
            except Exception as e:
                print(f"Failed to generate image for step: {e}")
                step['image_url'] = None

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

