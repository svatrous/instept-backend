from google import genai
from google.genai import types
import os
import time
import json
import hashlib
from models import Recipe, Step, Ingredient
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

client = genai.Client(api_key=api_key)

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(video_url: str, language: str) -> str:
    hash_object = hashlib.md5(video_url.encode())
    hash_hex = hash_object.hexdigest()
    return os.path.join(CACHE_DIR, f"{hash_hex}_{language}.json")

def save_recipe(recipe: Recipe, video_url: str, language: str):
    path = get_cache_path(video_url, language)
    with open(path, "w", encoding="utf-8") as f:
        f.write(recipe.json())

def get_cached_recipe(video_url: str, language: str) -> Recipe | None:
    path = get_cache_path(video_url, language)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Recipe(**data)
        except Exception as e:
            print(f"Failed to read cache: {e}")
            return None
    return None

def translate_recipe(recipe: Recipe, target_language: str) -> Recipe:
    print(f"Translating recipe to {target_language}...")
    prompt = f"""
    Translate this recipe JSON to language code '{target_language}'.
    Preserve the JSON structure exactly.
    Do NOT translate the keys.
    Do NOT translate image_url.
    Translate title, description, category, difficulty, time, calories, ingredient names, ingredient amounts, ingredient units, and step descriptions.
    
    Recipe JSON:
    {recipe.json()}
    
    Return ONLY valid JSON.
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        return Recipe(**data)
    except Exception as e:
        print(f"Translation failed: {e}")
        return recipe # Fallback to original

def analyze_video(video_path: str, video_url: str, language: str = "en") -> Recipe:
    """
    Uploads a video to Gemini and analyzes it to extract a recipe.
    Handles caching and translation.
    """
    
    # 1. Check cache for requested language
    cached = get_cached_recipe(video_url, language)
    if cached:
        print(f"Returning cached recipe for {language}")
        return cached

    # 2. Check cache for English (base)
    if language != "en":
        cached_en = get_cached_recipe(video_url, "en")
        if cached_en:
            print("Found English cache, translating...")
            translated = translate_recipe(cached_en, language)
            save_recipe(translated, video_url, language)
            return translated

    # 3. Analyze video (Force English output for consistency)
    print(f"Uploading file: {video_path}")
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
    Analyze this video and extract the recipe.
    Return the result in JSON format with the following structure:
    {
        "title": "Recipe Title",
        "description": "Short description (max 2 sentences)",
        "category": "Category (e.g., Breakfast, Lunch, Dinner, Dessert, Snack)",
        "time": "Total cooking time (e.g., 25 min)",
        "difficulty": "Difficulty level (Easy, Medium, Hard)",
        "calories": "Estimated calories per serving (e.g., 450)",
        "ingredients": [
            {"name": "Ingredient Name", "amount": "Amount", "unit": "Unit"}
        ],
        "steps": [
            {"description": "Step 1 description"},
            {"description": "Step 2 description"}
        ]
    }
    Ensure the output is valid JSON. Do not include markdown code blocks.
    Response MUST be in English.
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
        
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        # Add default/random values
        import random
        if "rating" not in data:
            data["rating"] = round(random.uniform(4.0, 5.0), 1)
        if "reviews_count" not in data:
            data["reviews_count"] = random.randint(50, 500)
        if "author_name" not in data:
            data["author_name"] = "Chef Mario"
        if "author_avatar" not in data:
            data["author_avatar"] = "https://i.pravatar.cc/150?u=chef"
        
        # Generate images for each step
        print("Generating images for steps...")
        for step in data.get("steps", []):
            try:
                image_prompt = f"Food photography, vertical 9:16 aspect ratio. Create a high quality, appetizing image for this recipe step: {step['description']}. The dish is {data.get('title')}. No text, no words, no letters."
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        image_response = client.models.generate_content(
                            model='gemini-3-pro-image-preview', 
                            contents=image_prompt,
                            config=types.GenerateContentConfig(
                                response_modalities=['IMAGE'],
                                image_config=types.ImageConfig(
                                    aspect_ratio="9:16",
                                    image_size="1K"
                                )
                            )
                        )

                        if image_response.parts:
                            saved = False
                            for part in image_response.parts:
                                if part.inline_data:
                                    img_data = part.inline_data.data
                                    filename = f"step_{int(time.time())}_{data['steps'].index(step)}.png"
                                    os.makedirs("static", exist_ok=True)
                                    with open(f"static/{filename}", "wb") as f:
                                        f.write(img_data)
                                    step['image_url'] = f"/static/{filename}"
                                    print(f"Generated image for step...")
                                    saved = True
                                    break
                            if saved: break
                    except Exception as e:
                        if "503" in str(e) or "429" in str(e):
                            if attempt < max_retries - 1:
                                time.sleep((attempt + 1) * 2)
                                continue
                        print(f"Failed to generate image: {e}")
                        step['image_url'] = None
                        break

            except Exception as e:
                print(f"Failed to process step image: {e}")
                step['image_url'] = None

        # Set hero image
        if data.get("steps") and data["steps"][0].get("image_url"):
            data["hero_image_url"] = data["steps"][0]["image_url"]

        base_recipe = Recipe(**data)
        save_recipe(base_recipe, video_url, "en") 
        
        if language != "en":
            translated = translate_recipe(base_recipe, language)
            save_recipe(translated, video_url, language)
            return translated
            
        return base_recipe
        
    except Exception as e:
        print(f"Error during generation: {e}")
        raise ValueError(f"Gemini generation failed: {e}")
        
    finally:
        try:
             client.files.delete(name=video_file.name)
        except Exception:
             pass
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
    Analyze this video and extract the recipe.
    Return the result in JSON format with the following structure:
    {
        "title": "Recipe Title",
        "description": "Short description (max 2 sentences)",
        "category": "Category (e.g., Breakfast, Lunch, Dinner, Dessert, Snack)",
        "time": "Total cooking time (e.g., 25 min)",
        "difficulty": "Difficulty level (Easy, Medium, Hard)",
        "calories": "Estimated calories per serving (e.g., 450)",
        "ingredients": [
            {"name": "Ingredient Name", "amount": "Amount", "unit": "Unit"}
        ],
        "steps": [
            {"description": "Step 1 description"},
            {"description": "Step 2 description"}
        ]
    }
    Ensure the output is valid JSON. Do not include markdown code blocks.
    Response MUST be in English.
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
        
        # Add default/random values for fields not extracted if missing
        import random
        if "rating" not in data:
            data["rating"] = round(random.uniform(4.0, 5.0), 1)
        if "reviews_count" not in data:
            data["reviews_count"] = random.randint(50, 500)
        if "author_name" not in data:
            data["author_name"] = "Chef Mario"
        if "author_avatar" not in data:
            data["author_avatar"] = "https://i.pravatar.cc/150?u=chef" # Placeholder or local asset later
        
        # Generate images for each step
        print("Generating images for steps...")
        for step in data.get("steps", []):
            try:
                image_prompt = f"Food photography, vertical 9:16 aspect ratio. Create a high quality, appetizing image for this recipe step: {step['description']}. The dish is {data.get('title')}. No text, no words, no letters."
                
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
                
                # Generate image using generate_content method for Gemini 3 Pro / 2.5 Flash Image
                # Model 'gemini-3-pro-image-preview' supports aspect ratio config
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        image_response = client.models.generate_content(
                            model='gemini-3-pro-image-preview', 
                            contents=image_prompt,
                            config=types.GenerateContentConfig(
                                response_modalities=['IMAGE'],
                                image_config=types.ImageConfig(
                                    aspect_ratio="9:16",
                                    image_size="1K"
                                )
                            )
                        )

                        # Saving image locally
                        if image_response.parts:
                            saved = False
                            for part in image_response.parts:
                                if part.inline_data:
                                    img_data = part.inline_data.data # This is bytes
                                    
                                    filename = f"step_{int(time.time())}_{data['steps'].index(step)}.png"
                                    os.makedirs("static", exist_ok=True)
                                    with open(f"static/{filename}", "wb") as f:
                                        f.write(img_data)
                                    
                                    step['image_url'] = f"/static/{filename}"
                                    print(f"Generated image for step: {step['description'][:20]}...")
                                    saved = True
                                    break # Only need one image
                            if saved:
                                break # Exit retry loop on success
                    except Exception as e:
                        if "503" in str(e) or "429" in str(e):
                            if attempt < max_retries - 1:
                                sleep_time = (attempt + 1) * 2
                                print(f"Generate failed with {e}, retrying in {sleep_time}s...")
                                time.sleep(sleep_time)
                                continue
                        print(f"Failed to generate content (image) for step: {e}")
                        step['image_url'] = None
                        break # Don't retry other errors or if retries exhausted

            except Exception as e:
                print(f"Failed to process step image: {e}")
                step['image_url'] = None

        # Set hero image to first step image if available
        if data.get("steps") and data["steps"][0].get("image_url"):
            data["hero_image_url"] = data["steps"][0]["image_url"]

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

