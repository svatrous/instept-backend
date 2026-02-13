from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from services.downloader import download_instagram_video
from services.gemini import analyze_video, get_cached_recipe
from services.firebase_service import update_recipe_rating
from models import Recipe, AnalyzeRequest

from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static directory for generated images
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/analyze", response_model=Recipe)
async def analyze_recipe(request: AnalyzeRequest):
    video_path = None
    try:
        # Check if we can skip download
        has_cache = get_cached_recipe(request.url, request.language) or \
                   (request.language != "en" and get_cached_recipe(request.url, "en"))

        if not has_cache:
            # 1. Download Video
            print(f"Downloading video from: {request.url}")
            video_path = download_instagram_video(request.url)
            print(f"Video downloaded to: {video_path}")
        else:
            print("Cache found, skipping download.")

        # 2. Analyze with Gemini
        print("Analyzing with Gemini...")
        recipe = analyze_video(video_path, request.url, request.language)
        return recipe

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            print("Cleaned up temporary video file.")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
