from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from services.downloader import download_instagram_video
from services.gemini import analyze_video
from models import Recipe, AnalyzeRequest

app = FastAPI()

@app.post("/analyze", response_model=Recipe)
async def analyze_recipe(request: AnalyzeRequest):
    video_path = None
    try:
        # 1. Download Video
        print(f"Downloading video from: {request.url}")
        video_path = download_instagram_video(request.url)
        print(f"Video downloaded to: {video_path}")

        # 2. Analyze with Gemini
        print("Analyzing with Gemini...")
        recipe = analyze_video(video_path)
        return recipe

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 3. Cleanup
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            print("Cleaned up temporary video file.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
