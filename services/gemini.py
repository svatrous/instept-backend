from google import genai
from google.genai import types
import os
import time
import json
import hashlib
from models import Recipe, Step, Ingredient
from dotenv import load_dotenv
from services.firebase_service import upload_image, save_recipe_to_firestore, get_recipe_from_firestore, generate_recipe_id

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set")

client = genai.Client(api_key=api_key)

# Local cache for translated/generated files is less important now, but we can keep it as backup if needed.
# For now, we will rely on Firestore check effectively serving as cache check if the document exists.

def get_cached_recipe(video_url: str, language: str) -> Recipe | None:
    existing_data = get_recipe_from_firestore(video_url)
    if existing_data:
        # 1. Check if exact language exists
        translations = existing_data.get('translations', {})
        if language in translations:
            print(f"Main: Found cached recipe for {language}")
            cached_recipe = Recipe(**translations[language])
            cached_recipe.id = generate_recipe_id(video_url)
            # Use global rating if available
            if 'rating' in existing_data:
                cached_recipe.rating = float(existing_data['rating'])
            if 'reviews_count' in existing_data:
                cached_recipe.reviews_count = int(existing_data['reviews_count'])
            cached_recipe.source_url = video_url
            if not cached_recipe.hero_image_url and existing_data.get('hero_image_url'):
                cached_recipe.hero_image_url = existing_data.get('hero_image_url')
            return cached_recipe
        
        # 2. Check if 'en' exists (base) - usually strictly speaking main.py logic check
        # But here we just return None if specific lang not found so main.py triggers analysis
        # WAIT: analyze_video ALSO checks cache. 
        # If we return None here, main.py downloads video, then calls analyze_video.
        # analyze_video checks cache again, finds base 'en', translates it, and returns.
        # SO: We downloaded video for nothing if 'en' exists but 'ru' doesn't!
        
        # Optimization: If ANY version exists, we don't need the video to translate!
        # analyze_video handles translation from base without video_path if base exists.
        # So we should return the BASE recipe here if target lang missing, 
        # and let analyze_video handle translation? 
        # NO, main.py expects a result to return immediately if not None.
        
        # If we return a Recipe here, main.py returns it.
        # If we return None, main.py downloads.
        
        # We need a way to tell main.py "Don't download, let analyze_video handle translation".
        # distinct from "Don't download, here is the result".
        
        # Actually, analyze_video signature: (video_path, video_url, language).
        # If video_path is None, it throws error UNLESS cache exists.
        # So we can just return True/False? No, main.py logic is:
        # if get_cached_recipe(...) returns valid Recipe -> return it.
        # else -> download -> analyze.
        
        # If we have 'en' but need 'ru': 
        # get_cached_recipe('ru') -> returns None (if we only look for 'ru').
        # main.py downloads.
        # analyze_video('ru') -> finds 'en', translates, saves 'ru'.
        # We wasted a download.
        
        # Solution: get_cached_recipe should return the TRANSLATED recipe if base exists!
        # valid? Yes, we can do translation here too or call analyze logic?
        # Better: analyze_video does the heavy lifting.
        # But analyze_video needs video_path if it *can't* find base.
        
        # If we change main.py to:
        # 1. Check if *any* cache exists (base).
        # 2. If yes -> skip download, call analyze_video(None, url, lang).
        # 3. If no -> download, call analyze_video(path, url, lang).
        
        # Let's DO THAT in main.py? 
        # Or make get_cached_recipe smart enough to translate?
        # Smart get_cached_recipe is better for encapsulation.
        
        if 'en' in translations:
             print(f"Main: Found base 'en' recipe, translating to {language}...")
             base_recipe = Recipe(**translations['en'])
             base_recipe.id = generate_recipe_id(video_url)
             # Use global rating if available
             if 'rating' in existing_data:
                 base_recipe.rating = float(existing_data['rating'])
             if 'reviews_count' in existing_data:
                 base_recipe.reviews_count = int(existing_data['reviews_count'])
             base_recipe.source_url = video_url
             if not base_recipe.hero_image_url and existing_data.get('hero_image_url'):
                 base_recipe.hero_image_url = existing_data.get('hero_image_url')

             translated = translate_recipe(base_recipe, language)
             # We should probably save it too?
             # Yes, save the translation.
             save_recipe_to_firestore(translated.dict(), video_url, language)
             translated.id = base_recipe.id
             return translated

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
    
    # 1. Check if recipe exists in Firestore
    existing_data = get_recipe_from_firestore(video_url)
    if existing_data:
        # Check if requested language exists in translations
        translations = existing_data.get('translations', {})
        if language in translations:
            print(f"Returning cached recipe for language: {language}")
            cached_recipe = Recipe(**translations[language])
            cached_recipe.id = generate_recipe_id(video_url)
            # Use global rating if available
            if 'rating' in existing_data:
                cached_recipe.rating = float(existing_data['rating'])
            if 'reviews_count' in existing_data:
                cached_recipe.reviews_count = int(existing_data['reviews_count'])
            cached_recipe.source_url = video_url
            # Restore hero image if not in translation but in main doc
            if not cached_recipe.hero_image_url and existing_data.get('hero_image_url'):
                cached_recipe.hero_image_url = existing_data.get('hero_image_url')
            return cached_recipe
        
        # If language not found, but we have English (or another base), use it as base for translation
        # Typically the 'base' recipe might not be stored separately if we only use translations map.
        # But our save logic puts 'translations' map. 
        # We can pick 'en' or any available language to translate FROM.
        base_lang = 'en'
        if base_lang in translations:
            print(f"Found base recipe in {base_lang}, translating to {language}...")
            base_recipe = Recipe(**translations[base_lang])
            base_recipe.id = generate_recipe_id(video_url)
            # Use global rating if available
            if 'rating' in existing_data:
                base_recipe.rating = float(existing_data['rating'])
            if 'reviews_count' in existing_data:
                base_recipe.reviews_count = int(existing_data['reviews_count'])
            base_recipe.source_url = video_url
            
            translated = translate_recipe(base_recipe, language)
            save_recipe_to_firestore(translated.dict(), video_url, language)
            translated.id = base_recipe.id
            return translated
            
    # If we are here, we need to process the video.
    if not video_path:
        # If no video path and no cache, we can't do anything
        raise ValueError("Video path is required for new analysis.")

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
            model="gemini-3-flash-preview",
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
        previous_images = []
        
        for i, step in enumerate(data.get("steps", [])):
            try:
                image_prompt = f"Food photography, vertical 9:16 aspect ratio. Create a high quality, appetizing image for this recipe step: {step['description']}. The dish is {data.get('title')}. No text, no words, no letters."
                
                # Build contents with context
                contents = []
                for prev_img_data in previous_images:
                    contents.append(types.Part.from_bytes(data=prev_img_data, mime_type="image/png"))
                contents.append(image_prompt)

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        image_response = client.models.generate_content(
                            model='gemini-3-pro-image-preview', 
                            contents=contents,
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
                                    
                                    # Store logic for next steps (limit to last 3 to save tokens/complexity if needed, or all)
                                    # The model supports up to 14 reference images.
                                    previous_images.append(img_data)
                                    
                                    # Save locally momentarily to upload
                                    temp_filename = f"step_{int(time.time())}_{i}.png"
                                    with open(temp_filename, "wb") as f:
                                        f.write(img_data)
                                    
                                    # Upload to Firebase Storage
                                    remote_url = upload_image(temp_filename, f"recipes/{generate_recipe_id(video_url)}/{temp_filename}")
                                    
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

            except Exception as e:
                print(f"Failed to process step image: {e}")
                step['image_url'] = None

        # Generate dedicated Hero Image
        print("Generating hero image...")
        try:
            hero_prompt = f"Food photography, vertical 9:16 aspect ratio. A cinematic, high-end hero shot of the final dish: {data.get('title')}. {data.get('description')}. The image should look like a professional magazine cover or cookbook photo. Make it appetizing and beautiful. No text."
            
            # Use all previous step images as context
            hero_contents = []
            for prev_img_data in previous_images:
                hero_contents.append(types.Part.from_bytes(data=prev_img_data, mime_type="image/png"))
            hero_contents.append(hero_prompt)
            
            hero_response = client.models.generate_content(
                model='gemini-3-pro-image-preview', 
                contents=hero_contents,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE'],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                        image_size="1024x1024"
                    )
                )
            )
            
            if hero_response.parts:
                for part in hero_response.parts:
                    if part.inline_data:
                        img_data = part.inline_data.data
                        
                        temp_filename = f"hero_{int(time.time())}.png"
                        with open(temp_filename, "wb") as f:
                            f.write(img_data)
                        
                        remote_url = upload_image(temp_filename, f"recipes/{generate_recipe_id(video_url)}/{temp_filename}")
                        
                        if remote_url:
                            data["hero_image_url"] = remote_url
                            print("Uploaded hero image")
                        else:
                            print("Failed to upload hero image")
                        
                        os.remove(temp_filename)
                        break
        except Exception as e:
            print(f"Failed to generate hero image: {e}")
            # Fallback to first step if hero gen fails
            if data.get("steps") and data["steps"][0].get("image_url"):
                data["hero_image_url"] = data["steps"][0]["image_url"]

        # If no hero image generated and no step images, it will remain None or handled by frontend placeholder

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

