from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class LookupObject(BaseModel):
    object: str = Field(..., description="Value to look up")

class Category(BaseModel):
    category: str
    detected_indicator: str
    context: Dict[str, Optional[str]]

class LookupResult(BaseModel):
    object: Optional[str] = None
    result: Optional[str] = None
    categories: Optional[List[Category]] = None

class LookupResultError(BaseModel):
    status: Optional[str] = None
    reason: Optional[str] = None