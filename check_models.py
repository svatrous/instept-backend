from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

try:
    print("Listing available models:")
    for model in client.models.list():
        print(f"- {model.name}: {model.display_name} (Supported actions: {model.supported_actions})")
except Exception as e:
    print(f"Error listing models: {e}")
