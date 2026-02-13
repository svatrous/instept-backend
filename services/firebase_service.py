import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import hashlib
import time

# Initialize Firebase Admin
try:
    cred = None
    # 1. Try local file
    cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase_credentials.json")
    if os.path.exists(cred_path):
        print(f"Loading Firebase credentials from file: {cred_path}")
        cred = credentials.Certificate(cred_path)
    
    # 2. Try environment variable (for deployment)
    elif os.getenv("FIREBASE_CREDENTIALS_JSON"):
        print("Loading Firebase credentials from FIREBASE_CREDENTIALS_JSON env var")
        # Parse JSON string from env var
        import json
        cred_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS_JSON"))
        cred = credentials.Certificate(cred_dict)
        
    if cred:
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{cred.project_id}.firebasestorage.app" 
        })
        print("Firebase Admin initialized successfully.")
    else:
        print(f"Warning: No Firebase credentials found (checked {cred_path} and FIREBASE_CREDENTIALS_JSON). Firebase features will be disabled.")
except Exception as e:
    print(f"Error initializing Firebase Admin: {e}")

def upload_image(file_path: str, destination_blob_name: str) -> str | None:
    """Uploads a file to the bucket and returns the public URL."""
    if not firebase_admin._apps:
        print("Firebase not initialized, skipping upload.")
        return None
        
    try:
        bucket = storage.bucket()
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)
        
        # Make public
        blob.make_public()
        print(f"File {file_path} uploaded to {destination_blob_name}.")
        return blob.public_url
    except Exception as e:
        print(f"Failed to upload image: {e}")
        return None

def save_recipe_to_firestore(recipe_data: dict, source_url: str, language: str) -> str | None:
    """
    Saves or updates a recipe in Firestore.
    Returns the document ID.
    """
    if not firebase_admin._apps:
        print("Firebase not initialized, skipping Firestore save.")
        return None
        
import re

def generate_recipe_id(source_url: str) -> str:
    """
    Generates a unique ID for the recipe based on the source URL.
    For Instagram, it tries to extract the shortcode (e.g. from /reel/SHORTCODE).
    Falls back to hashing the URL without query parameters.
    """
    # Try to extract Instagram shortcode
    # Matches /reel/CODE or /p/CODE
    match = re.search(r'instagram\.com/(?:reel|p)/([^/?#]+)', source_url)
    if match:
        unique_key = match.group(1)
        # print(f"Extracted Instagram key: {unique_key}")
    else:
        # Fallback: remove query params
        unique_key = source_url.split('?')[0].split('#')[0]
    
    return hashlib.md5(unique_key.encode()).hexdigest()

def save_recipe_to_firestore(recipe_data: dict, source_url: str, language: str) -> str | None:
    """
    Saves or updates a recipe in Firestore.
    Returns the document ID.
    """
    if not firebase_admin._apps:
        print("Firebase not initialized, skipping Firestore save.")
        return None
        
    try:
        db = firestore.client()
        
        # Generate ID
        recipe_id = generate_recipe_id(source_url)
        
        doc_ref = db.collection('recipes').document(recipe_id)
        doc = doc_ref.get()
        
        if doc.exists:
            # Update existing document: merge translation
            print(f"Updating existing recipe {recipe_id} for language {language}")
            doc_ref.set({
                'translations': {
                    language: recipe_data
                }
            }, merge=True)
            return recipe_id
        else:
            # Create new document
            print(f"Creating new recipe {recipe_id}")
            
            # Structure for Firestore
            new_recipe = {
                'source_url': source_url,
                'created_at': firestore.SERVER_TIMESTAMP,
                'translations': {
                    language: recipe_data
                },
                # Flatten some metadata for easier querying if needed
                'metadata': {
                    'author_name': recipe_data.get('author_name'),
                    'time': recipe_data.get('time'),
                    'category': recipe_data.get('category')
                }
            }
            
            # Add hero image if available in the recipe data (it might be in steps)
            if recipe_data.get('hero_image_url'):
                 new_recipe['hero_image_url'] = recipe_data.get('hero_image_url')
            
            doc_ref.set(new_recipe)
            return recipe_id
            
    except Exception as e:
        print(f"Failed to save recipe to Firestore: {e}")
        return None

def get_recipe_from_firestore(source_url: str) -> dict | None:
    """
    Fetches a recipe from Firestore by source URL hash.
    Returns the document data if it exists, else None.
    """
    if not firebase_admin._apps:
        return None
        
    try:
        db = firestore.client()
        recipe_id = generate_recipe_id(source_url)
        doc_ref = db.collection('recipes').document(recipe_id)
        doc = doc_ref.get()
        
        if doc.exists:
            print(f"Found existing recipe {recipe_id} in Firestore")
            return doc.to_dict()
        else:
            return None
    except Exception as e:
        print(f"Failed to fetch recipe from Firestore: {e}")
        return None
