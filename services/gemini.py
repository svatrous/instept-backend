from google import genai
from google.genai import types
import os
import time
import json
import hashlib
from models import Recipe, Step, Ingredient
from dotenv import load_dotenv
from services.firebase_service import upload_image, save_recipe_to_firestore

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

client = genai.Client(api_key=api_key)

# Local cache for translated/generated files is less important now, but we can keep it as backup if needed.
# For now, we will rely on Firestore check effectively serving as cache check if the document exists.

def get_cached_recipe(video_url: str, language: str) -> Recipe | None:
    # TODO: Implement Firestore fetch as cache check if needed.
    # For now, we assume if we hit analyze endpoint, we might want fresh check or handle it in main.py
    # But main.py calls this. Let's return None to force re-analysis or fetch from Firestore if we implement read.
    # Given the task, we are moving STORAGE to Firebase.
    # The `main.py` logic checks cache to avoid re-downloading.
    # We can leave local file check for now to not break existing flow, OR update to check Firestore.
    # Let's keep existing local check as a "hot" cache for development, but in production we'd check Firestore.
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
            model="gemini-2.0-flash", # Use faster model for translation
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        # Handle case where Gemini returns a list instead of a dict
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                data = data[0]
            else:
                # Try to find a dict in the list that looks like a recipe? 
                # Or just error out gracefully
                print("Translation returned a list without a valid dict")
                return recipe

        # Preserve original images/metadata
        translated_recipe = Recipe(**data)
        translated_recipe.id = recipe.id
        translated_recipe.source_url = recipe.source_url
        translated_recipe.hero_image_url = recipe.hero_image_url
        translated_recipe.steps = [
            Step(description=s.description, image_url=orig_s.image_url) 
            for s, orig_s in zip(translated_recipe.steps, recipe.steps)
        ]
        
        return translated_recipe
    except Exception as e:
        print(f"Translation failed: {e}")
        return recipe # Fallback to original

def analyze_video(video_path: str | None, video_url: str, language: str = "en") -> Recipe:
    """
    Uploads a video to Gemini and analyzes it to extract a recipe.
    Handles caching and translation.
    """
    
    # 1. Check if recipe exists in Firestore (optional optimization, but let's proceed to analyze or just translate)
    # Ideally we'd check Firestore here.
    
    # If we are here, we need to process the video.
    if not video_path:
        raise ValueError("Video path is required.")

    # 3. Analyze video
    print(f"Uploading file: {video_path}")
    video_file = client.files.upload(file=video_path)
    print(f"Completed upload: {video_file.name}")

    # Wait for processing
    while video_file.state == "PROCESSING":
        print('.', end='', flush=True)
        time.sleep(2)
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
            model="gemini-2.0-flash",
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
        for i, step in enumerate(data.get("steps", [])):
            try:
                image_prompt = f"Food photography, vertical 9:16 aspect ratio. Create a high quality, appetizing image for this recipe step: {step['description']}. The dish is {data.get('title')}. No text, no words, no letters."
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        image_response = client.models.generate_content(
                            model='gemini-2.5-flash-image', 
                            contents=image_prompt,
                            config=types.GenerateContentConfig(
                                response_modalities=['IMAGE'],
                                image_config=types.ImageConfig(
                                    aspect_ratio="9:16",
                                    image_size="1024x1024"
                                )
                            )
                        )

                        if image_response.parts:
                            saved = False
                            for part in image_response.parts:
                                if part.inline_data:
                                    img_data = part.inline_data.data
                                    
                                    # Save locally momentarily to upload
                                    temp_filename = f"step_{int(time.time())}_{i}.png"
                                    with open(temp_filename, "wb") as f:
                                        f.write(img_data)
                                    
                                    # Upload to Firebase Storage
                                    remote_url = upload_image(temp_filename, f"recipes/{hashlib.md5(video_url.encode()).hexdigest()}/{temp_filename}")
                                    
                                    if remote_url:
                                        step['image_url'] = remote_url
                                        print(f"Uploaded image for step {i}")
                                    else:
                                        print(f"Failed to upload image for step {i}")
                                    
                                    # Cleanup local file
                                    os.remove(temp_filename)
                                    
                                    saved = True
                                    break
                            if saved: break
                    except Exception as e:
                        if "503" in str(e) or "429" in str(e):
                            if attempt < max_retries - 1:
                                time.sleep((attempt + 1) * 2)
                                continue
                        print(f"Failed to generate/upload image: {e}")
                        step['image_url'] = None
                        break

            except Exception as e:
                print(f"Failed to process step image: {e}")
                step['image_url'] = None

        # Set hero image
        if data.get("steps") and data["steps"][0].get("image_url"):
            data["hero_image_url"] = data["steps"][0]["image_url"]

        base_recipe = Recipe(**data)
        base_recipe.source_url = video_url
        
        # Save to Firestore (English)
        firestore_id = save_recipe_to_firestore(base_recipe.dict(), video_url, "en")
        base_recipe.id = firestore_id
        
        # Translate if needed
        if language != "en":
            translated = translate_recipe(base_recipe, language)
            
            # Save translated version to Firestore (merge into translations)
            save_recipe_to_firestore(translated.dict(), video_url, language)
            translated.id = firestore_id
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

