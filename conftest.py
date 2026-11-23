"""pytest settings: the tests never call the weather service on the internet."""
import os

os.environ.setdefault("WEATHER_AUTO", "0")
