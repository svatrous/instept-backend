from pydantic import BaseModel, field_validator
from typing import List, Optional

class Ingredient(BaseModel):
    name: str
    amount: str
    unit: str

class Step(BaseModel):
    description: str
    image_url: Optional[str] = None

class Recipe(BaseModel):
    id: Optional[str] = None
    source_url: Optional[str] = None
    title: str
    description: str
    category: str = "Dinner"
    rating: float = 4.8
    reviews_count: int = 124
    time: str = "30 min"
    difficulty: str = "Medium"
    calories: str = "450"
    author_name: str = "Chef Mario"
    author_avatar: str = "" # URL to avatar
    hero_image_url: Optional[str] = None
    created_at: Optional[str] = None # ISO format or timestamp
    likes_count: int = 0
    ingredients: List[Ingredient]
    steps: List[Step]
    language: str = "en"

    @field_validator('calories', 'time', 'difficulty', 'category', mode='before')
    @classmethod
    def coerce_to_string(cls, v):
        return str(v)

class AnalyzeRequest(BaseModel):
    url: str
    language: str = "en"
    fcm_token: Optional[str] = None
