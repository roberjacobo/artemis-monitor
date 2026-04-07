import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "10"))
LAUNCH_DATE = datetime.fromisoformat(
    os.getenv("LAUNCH_DATE", "2026-06-01T00:00:00+00:00")
)
