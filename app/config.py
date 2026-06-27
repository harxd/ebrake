import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent

# User-customizable directories via environment variables
APPDATA_DIR = Path(os.getenv("EBRAKE_APPDATA_DIR", str(BASE_DIR / "appdata"))).resolve()
MEDIA_DIR = Path(os.getenv("EBRAKE_MEDIA_DIR", str(BASE_DIR / "media"))).resolve()

# Derived directories
DB_DIR = APPDATA_DIR / "db"
DB_PATH = DB_DIR / "ebrake.db"
PRESETS_DIR = APPDATA_DIR / "presets"
TEMP_DIR = APPDATA_DIR / "temp"

def init_directories():
    """Ensure all required application directories exist."""
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create a default "Default" category folder if it's empty
    default_cat = PRESETS_DIR / "Default"
    default_cat.mkdir(parents=True, exist_ok=True)
