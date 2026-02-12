from pydantic import BaseModel
from typing import List, Optional

class Ingredient(BaseModel):
    name: str
    amount: str
    unit: str

class Step(BaseModel):
    description: str
    image_url: Optional[str] = None

class Recipe(BaseModel):
    title: str
    description: str
    ingredients: List[Ingredient]
    steps: List[Step]

class AnalyzeRequest(BaseModel):
    url: str
