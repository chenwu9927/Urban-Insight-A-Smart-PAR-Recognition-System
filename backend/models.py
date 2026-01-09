from pydantic import BaseModel
from typing import List, Optional

class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

class PedestrianAttribute(BaseModel):
    gender: str
    age_group: str
    upper_color: str
    lower_color: str
    has_backpack: bool
    confidence: float

class RecognitionResult(BaseModel):
    pedestrian_id: str
    bbox: BoundingBox
    attributes: PedestrianAttribute

class AnalysisResponse(BaseModel):
    filename: str
    pedestrians: List[RecognitionResult]
