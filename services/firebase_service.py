import firebase_admin
from firebase_admin import credentials, firestore, storage
import os
import hashlib
import time

# Initialize Firebase Admin
try:
    cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase_credentials.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': f"{cred.project_id}.firebasestorage.app" 
        })
        print("Firebase Admin initialized successfully.")
    else:
        print(f"Warning: firebase_credentials.json not found at {cred_path}. Firebase features will be disabled.")
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
        
    try:
        db = firestore.client()
        
        # Generate ID based on URL hash to avoid duplicates
        recipe_id = hashlib.md5(source_url.encode()).hexdigest()
        
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
