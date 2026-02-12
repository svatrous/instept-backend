from pydantic import BaseModel
from typing import List, Optional

class Ingredient(BaseModel):
    name: str
    amount: str
    unit: str

class Recipe(BaseModel):
    title: str
    description: str
    ingredients: List[Ingredient]
    steps: List[str]

class AnalyzeRequest(BaseModel):
    url: str
