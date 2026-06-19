import os
import time
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any
from app.config import MEDIA_DIR
from app.database import sync_media_files_db

logger = logging.getLogger(__name__)

# Control flag for manual sync block
is_syncing = False

def scan_media_directory() -> List[Dict[str, Any]]:
    """
    Recursively scans the media directory using os.scandir.
    Returns a list of dictionaries prepared for SQLite upsert.
    """
    results = []
    
    if not MEDIA_DIR.exists():
        logger.warning(f"Media directory {MEDIA_DIR} does not exist.")
        return results

    # Queue for directories to scan
    dirs_to_scan = [MEDIA_DIR]
    
    while dirs_to_scan:
        current_dir = dirs_to_scan.pop()
        try:
            with os.scandir(current_dir) as it:
                for entry in it:
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        is_dir = entry.is_dir(follow_symlinks=False)
                        
                        entry_path = Path(entry.path).resolve()
                        parent_path = entry_path.parent
                        
                        item = {
                            "path": str(entry_path),
                            "name": entry.name,
                            "parent_path": str(parent_path),
                            "is_dir": 1 if is_dir else 0,
                            "size": stat.st_size if not is_dir else 0,
                            "mtime": stat.st_mtime
                        }
                        results.append(item)
                        
                        if is_dir:
                            dirs_to_scan.append(entry_path)
                    except OSError as e:
                        # Skip files/folders that we can't access
                        logger.error(f"Error reading entry {entry.name}: {e}")
        except OSError as e:
            logger.error(f"Error accessing directory {current_dir}: {e}")
            
    return results

def run_library_sync():
    """
    Synchronously scan the media directory and update the database index.
    Thread-safe and runs outside the async loop if needed.
    """
    global is_syncing
    if is_syncing:
        logger.warning("Library sync already in progress.")
        return
        
    is_syncing = True
    start_time = time.time()
    logger.info("Starting background media folder scan...")
    try:
        files = scan_media_directory()
        logger.info(f"Scan complete. Discovered {len(files)} files/directories. Updating database...")
        sync_media_files_db(files)
        logger.info(f"Database sync complete in {time.time() - start_time:.2f} seconds.")
    except Exception as e:
        logger.error(f"Library sync failed: {e}")
    finally:
        is_syncing = False

async def start_periodic_scanner(interval_seconds: int = 1800):
    """
    Run library sync periodically.
    Runs on startup in the background of FastAPI.
    """
    # Wait a few seconds on startup before running first scan
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("Triggering periodic background library sync...")
            # Run in thread executor because scan_media_directory does blocking I/O
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_library_sync)
        except Exception as e:
            logger.error(f"Error in periodic library sync loop: {e}")
        await asyncio.sleep(interval_seconds)

def is_library_syncing() -> bool:
    """Return the live status of the background library sync."""
    return is_syncing
