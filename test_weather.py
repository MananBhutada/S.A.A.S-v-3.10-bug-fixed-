"""
test_weather.py  (project root)
Project S.A.A.S. — Quick weather service check
===============================================
Run:  python test_weather.py

Fix applied: sys.path setup added so 'services' is importable when run
from the project root (or any directory).
"""

import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from services.weather_service import get_weather

weather = get_weather("Pune")
print(weather)
