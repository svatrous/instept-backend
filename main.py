from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os
from services.downloader import download_instagram_video
from services.gemini import analyze_video, get_cached_recipe
from services.firebase_service import update_recipe_rating, send_push_notification
from models import Recipe, AnalyzeRequest

from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static directory for generated images
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ProcessingResponse(BaseModel):
    status: str
    message: str
    recipe_id: str | None = None

def process_video_background(url: str, language: str, fcm_token: str | None):
    """
    Background task to process video and send push notification.
    """
    video_path = None
    try:
        print(f"Starting background processing for: {url}")
        
        # Check cache first
        has_cache = get_cached_recipe(url, language) or \
                   (language != "en" and get_cached_recipe(url, "en"))

        recipe = None
        if not has_cache:
            # 1. Download Video
            print(f"Downloading video from: {url}")
            video_path = download_instagram_video(url)
            print(f"Video downloaded to: {video_path}")
        else:
            print("Cache found, skipping download.")

        # 2. Analyze with Gemini (this saves to Firestore internally)
        print("Analyzing with Gemini...")
        recipe = analyze_video(video_path, url, language)
        
        print(f"Background processing complete. Recipe ID: {recipe.id}")
        
        # 3. Send Push Notification
        if fcm_token and recipe:
            send_push_notification(
                token=fcm_token,
                title="Recipe Ready! 🍳",
                body=f"Your recipe '{recipe.title}' is ready to cook.",
                data={
                    "recipe_id": recipe.id,
                    "type": "recipe_ready"
                }
            )
            
    except Exception as e:
        print(f"Background processing failed: {e}")
        # Send error notification
        if fcm_token:
            send_push_notification(
                token=fcm_token,
                title="Processing Failed 😕",
                body="We couldn't extract a recipe from that video. Please try another one.",
                data={
                    "type": "error",
                    "error": str(e)
                }
            )
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                print("Cleaned up temporary video file.")
            except:
                pass

@app.post("/analyze", response_model=ProcessingResponse)
async def analyze_recipe(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    # Check if we have a direct cache hit to return immediately?
    # Actually, for "processing screen" flow, we might WANT to show it even if fast?
    # But if it's cached, might be nice to return immediately.
    # However, to keep clients simple, let's ALWAYS return "processing" 
    # and let the push notification (or polling) handle it?
    # OR: If cached, return status="completed" and the recipe_id?
    
    # Let's try to be smart. If cached, we can return fast.
    # But currently verify_video downloads if not cached. 
    # Let's just offload EVERYTHING to background to match the requested UI flow.
    # The user wants "Processing View" -> "Push Notification".
    
    background_tasks.add_task(
        process_video_background, 
        request.url, 
        request.language, 
        request.fcm_token
    )
    
    return ProcessingResponse(
        status="processing",
        message="Recipe import started in background."
    )

class RateRequest(BaseModel):
    recipe_id: str
    rating: int

@app.post("/rate")
async def rate_recipe(request: RateRequest):
    print(f"Rating recipe {request.recipe_id} with {request.rating}")
    result = update_recipe_rating(request.recipe_id, request.rating)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to update rating")
    return result

@app.post("/translate", response_model=Recipe)
async def translate_recipe_endpoint(request: AnalyzeRequest):
    """
    Translates an existing recipe to the target language.
    """
    print(f"Translation request for {request.url} to {request.language}")
    
    # get_cached_recipe handles finding the base recipe and translating it if needed
    recipe = get_cached_recipe(request.url, request.language)
    
    if recipe:
        return recipe
        
    raise HTTPException(status_code=404, detail="Recipe not found. Please analyze it first.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
