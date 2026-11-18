"""Speech runtime locations without importing dataset/training dependencies."""
import os
from pathlib import Path

CACHE = Path(os.environ.get("FLIGHT_RIGHT_VOICE_CACHE",
                           Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"))
SR = 16_000
