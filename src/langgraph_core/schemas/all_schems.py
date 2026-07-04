from typing import Literal

from pydantic import BaseModel, Field


class WindInfo(BaseModel):
    speed: float = Field(..., description="Wind speed in km/h")
    direction: int = Field(..., description="Wind direction in radian, e.g., 258'")


class WeatherResponse(BaseModel):
    city: str
    temp: float
    unit: Literal["Celsius", "Fahrenheit", "Kelvin"]
    wind: WindInfo
