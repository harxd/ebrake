import toml
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import PRESETS_DIR

logger = logging.getLogger(__name__)

def init_presets():
    """Ensure presets directory has some basic starting presets if empty."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    categories = list_categories()
    
    if not categories or (len(categories) == 1 and not list_presets(categories[0])):
        # Empty preset list, create default category and presets
        default_cat = PRESETS_DIR / "Default"
        default_cat.mkdir(parents=True, exist_ok=True)
        
        # AV1 High Quality preset
        av1_preset = {
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
                "container": "mkv",
                "save_info_file": False
            }
        }
        
        # H.264 Fast 1080p preset
        h264_preset = {
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
                "container": "mp4",
                "save_info_file": False
            }
        }
        
        try:
            with open(default_cat / "AV1 VMAF Auto-CRF.ebrake", "w") as f:
                toml.dump(av1_preset, f)
            with open(default_cat / "H264 1080p Fast.ebrake", "w") as f:
                toml.dump(h264_preset, f)
            logger.info("Initialized default preset templates.")
        except Exception as e:
            logger.error(f"Failed to write default presets: {e}")

def list_categories() -> List[str]:
    """List category directory names under presets folder."""
    if not PRESETS_DIR.exists():
        return []
    return [p.name for p in PRESETS_DIR.iterdir() if p.is_dir()]

def create_category(category_name: str) -> bool:
    """Create a new category directory."""
    # Clean the category name of slashes/dots to prevent path traversal
    clean_name = Path(category_name).name
    if not clean_name:
        return False
    cat_dir = PRESETS_DIR / clean_name
    cat_dir.mkdir(parents=True, exist_ok=True)
    return True

def delete_category(category_name: str) -> bool:
    """Delete a category and its presets recursive."""
    clean_name = Path(category_name).name
    cat_dir = PRESETS_DIR / clean_name
    if cat_dir.exists() and cat_dir.is_dir():
        shutil.rmtree(cat_dir)
        return True
    return False

def list_presets(category: str) -> List[str]:
    """List presets inside a specific category."""
    clean_cat = Path(category).name
    cat_dir = PRESETS_DIR / clean_cat
    if not cat_dir.exists() or not cat_dir.is_dir():
        return []
    return [p.stem for p in cat_dir.glob("*.ebrake")]

def get_preset(category: str, name: str) -> Optional[Dict[str, Any]]:
    """Load and parse preset TOML configurations."""
    clean_cat = Path(category).name
    clean_name = Path(name).name
    preset_path = PRESETS_DIR / clean_cat / f"{clean_name}.ebrake"
    
    if not preset_path.exists():
        return None
        
    try:
        with open(preset_path, "r") as f:
            data = toml.load(f)
            # Ensure standard sections exist to prevent UI crashes
            data.setdefault("video", {})
            data.setdefault("audio", {})
            data.setdefault("subtitles", {})
            data.setdefault("optimization", {})
            data.setdefault("output", {})
            return data
    except Exception as e:
        logger.error(f"Error reading preset TOML: {e}")
        return None

def save_preset(category: str, name: str, preset_data: Dict[str, Any]) -> bool:
    """Save a preset configurations as TOML."""
    clean_cat = Path(category).name
    # Strip `.ebrake` if included in name
    clean_name = Path(name).stem
    
    cat_dir = PRESETS_DIR / clean_cat
    if not cat_dir.exists() or not cat_dir.is_dir():
        return False
        
    preset_path = cat_dir / f"{clean_name}.ebrake"
    try:
        with open(preset_path, "w") as f:
            toml.dump(preset_data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving preset TOML: {e}")
        return False

def delete_preset(category: str, name: str) -> bool:
    """Delete a preset `.ebrake` file."""
    clean_cat = Path(category).name
    clean_name = Path(name).name
    preset_path = PRESETS_DIR / clean_cat / f"{clean_name}.ebrake"
    
    if preset_path.exists():
        preset_path.unlink()
        return True
    return False

def get_all_presets() -> Dict[str, List[str]]:
    """Return dictionary of categories with their presets list."""
    result = {}
    for cat in list_categories():
        result[cat] = list_presets(cat)
    return result
