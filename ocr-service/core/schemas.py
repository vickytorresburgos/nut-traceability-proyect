from typing import TypedDict

class RemitoData(TypedDict):
    raw_text: str
    farm_name: str | None
    harvest_type: str | None
    date: str | None
    confidence: float
    confidence_alert: bool

class OvenData(TypedDict):
    raw_text: str
    oven_id: str | None
    humidity: str | None
    confidence: float
    confidence_alert: bool
    errors: list

class CaliberData(TypedDict):
    raw_text: str
    caliber: str | None
    weight: str | None
    confidence: float
    confidence_alert: bool
