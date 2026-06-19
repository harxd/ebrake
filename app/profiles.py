import toml
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import PROFILES_DIR

logger = logging.getLogger(__name__)

def init_profiles():
    """Ensure profiles directory has some basic starting presets if empty."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    categories = list_categories()
    
    if not categories or (len(categories) == 1 and not list_profiles(categories[0])):
        # Empty profile list, create default category and profiles
        default_cat = PROFILES_DIR / "Default"
        default_cat.mkdir(parents=True, exist_ok=True)
        
        # AV1 High Quality profile
        av1_profile = {
            "video": {
                "codec": "libsvtav1",
                "preset": "6",
                "crf": 24,
                "visual_tune": 0,
                "fps": "same as source",
                "fps_mode": "variable",
                "pixel_format": "yuv420p10le"
            },
            "optimization": {
                "target_vmaf": 95.0,
                "vmaf_search_range": [18, 30],
                "duplicate_frame_detection": True,
                "duplicate_threshold": 0.001
            },
            "audio": {
                "passthrough_codecs": ["aac", "ac3", "dts", "eac3", "truehd", "flac"],
                "fallback_codec": "aac",
                "fallback_bitrate": 192000
            },
            "subtitles": {
                "mode": "passthrough",
                "languages": ["all"],
                "burn_in_track_select": "default"
            },
            "output": {
                "output_suffix": "-av1-vmaf",
                "container": "mkv"
            }
        }
        
        # H.264 Fast 1080p profile
        h264_profile = {
            "video": {
                "codec": "libx264",
                "preset": "fast",
                "crf": 22,
                "visual_tune": 0,
                "fps": "same as source",
                "fps_mode": "constant",
                "pixel_format": "yuv420p"
            },
            "optimization": {
                "target_vmaf": 0.0, # disabled
                "vmaf_search_range": [18, 28],
                "duplicate_frame_detection": False,
                "duplicate_threshold": 0.001
            },
            "audio": {
                "passthrough_codecs": ["aac", "ac3", "mp3"],
                "fallback_codec": "aac",
                "fallback_bitrate": 128000
            },
            "subtitles": {
                "mode": "none",
                "languages": ["eng"],
                "burn_in_track_select": "default"
            },
            "output": {
                "output_suffix": "-1080p-fast",
                "container": "mp4"
            }
        }
        
        try:
            with open(default_cat / "AV1 VMAF Auto-CRF.ebrake", "w") as f:
                toml.dump(av1_profile, f)
            with open(default_cat / "H264 1080p Fast.ebrake", "w") as f:
                toml.dump(h264_profile, f)
            logger.info("Initialized default profile templates.")
        except Exception as e:
            logger.error(f"Failed to write default profiles: {e}")

def list_categories() -> List[str]:
    """List category directory names under profiles folder."""
    if not PROFILES_DIR.exists():
        return []
    return [p.name for p in PROFILES_DIR.iterdir() if p.is_dir()]

def create_category(category_name: str) -> bool:
    """Create a new category directory."""
    # Clean the category name of slashes/dots to prevent path traversal
    clean_name = Path(category_name).name
    if not clean_name:
        return False
    cat_dir = PROFILES_DIR / clean_name
    cat_dir.mkdir(parents=True, exist_ok=True)
    return True

def delete_category(category_name: str) -> bool:
    """Delete a category and its profiles recursive."""
    clean_name = Path(category_name).name
    cat_dir = PROFILES_DIR / clean_name
    if cat_dir.exists() and cat_dir.is_dir():
        shutil.rmtree(cat_dir)
        return True
    return False

def list_profiles(category: str) -> List[str]:
    """List profiles inside a specific category."""
    clean_cat = Path(category).name
    cat_dir = PROFILES_DIR / clean_cat
    if not cat_dir.exists() or not cat_dir.is_dir():
        return []
    return [p.stem for p in cat_dir.glob("*.ebrake")]

def get_profile(category: str, name: str) -> Optional[Dict[str, Any]]:
    """Load and parse profile TOML configurations."""
    clean_cat = Path(category).name
    clean_name = Path(name).name
    profile_path = PROFILES_DIR / clean_cat / f"{clean_name}.ebrake"
    
    if not profile_path.exists():
        return None
        
    try:
        with open(profile_path, "r") as f:
            data = toml.load(f)
            # Ensure standard sections exist to prevent UI crashes
            data.setdefault("video", {})
            data.setdefault("audio", {})
            data.setdefault("subtitles", {})
            data.setdefault("optimization", {})
            data.setdefault("output", {})
            return data
    except Exception as e:
        logger.error(f"Error reading profile TOML: {e}")
        return None

def save_profile(category: str, name: str, profile_data: Dict[str, Any]) -> bool:
    """Save a profile configurations as TOML."""
    clean_cat = Path(category).name
    # Strip `.ebrake` if included in name
    clean_name = Path(name).stem
    
    cat_dir = PROFILES_DIR / clean_cat
    if not cat_dir.exists() or not cat_dir.is_dir():
        return False
        
    profile_path = cat_dir / f"{clean_name}.ebrake"
    try:
        with open(profile_path, "w") as f:
            toml.dump(profile_data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving profile TOML: {e}")
        return False

def delete_profile(category: str, name: str) -> bool:
    """Delete a profile `.ebrake` file."""
    clean_cat = Path(category).name
    clean_name = Path(name).name
    profile_path = PROFILES_DIR / clean_cat / f"{clean_name}.ebrake"
    
    if profile_path.exists():
        profile_path.unlink()
        return True
    return False

def get_all_profiles() -> Dict[str, List[str]]:
    """Return dictionary of categories with their profiles list."""
    result = {}
    for cat in list_categories():
        result[cat] = list_profiles(cat)
    return result
