import sqlite3
import json
import logging
from contextlib import contextmanager
from typing import Dict, Any, List, Optional
from app.config import DB_PATH

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

@contextmanager
def db_conn():
    """Context manager for SQLite database connection. Uses Row factory."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize database tables and default settings."""
    with db_conn() as conn:
        # Jobs Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            finished_at DATETIME,
            failed_at DATETIME,
            cancelled_at DATETIME,
            duration INTEGER,
            relative_size INTEGER,
            input_path TEXT NOT NULL,
            output_path TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 0,
            transcode_next_position INTEGER UNIQUE, -- NULL allowed, values are 0-indexed sequence numbers
            category TEXT,
            preset TEXT,
            is_customized BOOLEAN NOT NULL DEFAULT 0 CHECK(is_customized IN (0, 1)),
            preset_config TEXT, -- JSON string containing final resolved profile params
            subtitle_mode TEXT NOT NULL CHECK(subtitle_mode IN ('none', 'passthrough', 'burn-in')),
            selected_subtitle_track INTEGER,
            ffmpeg TEXT,
            error TEXT,
            source_fps REAL,
            unduplicated_fps REAL,
            result_fps REAL,
            target_vmaf REAL,
            selected_crf INTEGER,
            measured_vmaf REAL
        );
        """)

        # Media Files Table (Search Cache)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS media_files (
            path TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent_path TEXT NOT NULL,
            is_dir BOOLEAN NOT NULL CHECK(is_dir IN (0, 1)),
            size INTEGER NOT NULL DEFAULT 0,
            mtime REAL NOT NULL -- modification timestamp as float
        );
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_files_name ON media_files(name);")

        # Settings Table (Persistent Key-Value Store)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL -- Serialized value (e.g. JSON string or plain text)
        );
        """)

        # Insert Default System Settings
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('on_startup_orphaned_job_action', '\"mark_failed_pause\"');")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('privacy_mode_enabled', 'false');")

# Settings Helpers
def get_setting(key: str, default: Any = None) -> Any:
    """Retrieve a setting by key and deserialize it from JSON."""
    try:
        with db_conn() as conn:
            cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return json.loads(row["value"])
    except Exception as e:
        logger.error(f"Error fetching setting {key}: {e}")
    return default

def set_setting(key: str, value: Any):
    """Serialize a value as JSON and save it in the settings table."""
    val_str = json.dumps(value)
    with db_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val_str))

# Jobs Helpers
def get_jobs(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch jobs matching status (or all if None) in execution order."""
    with db_conn() as conn:
        if status == 'pending':
            # Unified queue sorting logic
            cur = conn.execute("""
            SELECT *
            FROM jobs
            WHERE status = 'pending'
            ORDER BY
              CASE WHEN transcode_next_position IS NOT NULL THEN 0 ELSE 1 END ASC,
              transcode_next_position ASC,
              priority DESC,
              created_at ASC;
            """)
        elif status:
            cur = conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cur = conn.execute("""
            SELECT * FROM jobs
            ORDER BY 
              CASE 
                WHEN status = 'running' THEN 0 
                WHEN status = 'pending' THEN 1 
                ELSE 2 
              END ASC,
              CASE WHEN transcode_next_position IS NOT NULL THEN 0 ELSE 1 END ASC,
              transcode_next_position ASC,
              priority DESC,
              created_at DESC;
            """)
        return [dict(row) for row in cur.fetchall()]

def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    """Fetch job by ID."""
    with db_conn() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def create_job(job_data: Dict[str, Any]) -> int:
    """Create a new job and return its ID."""
    fields = list(job_data.keys())
    placeholders = ", ".join(["?"] * len(fields))
    sql = f"INSERT INTO jobs ({', '.join(fields)}) VALUES ({placeholders})"
    
    with db_conn() as conn:
        cur = conn.execute(sql, tuple(job_data[f] for f in fields))
        return cur.lastrowid

def update_job(job_id: int, **kwargs) -> bool:
    """Update specific columns of a job."""
    if not kwargs:
        return False
    
    # Always update updated_at if not explicitly set
    if 'updated_at' not in kwargs:
        kwargs['updated_at'] = sqlite3.datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = [f"{k} = ?" for k in kwargs.keys()]
    sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
    
    with db_conn() as conn:
        cur = conn.execute(sql, tuple(kwargs[k] for k in kwargs.keys()) + (job_id,))
        return cur.rowcount > 0

def delete_job(job_id: int) -> bool:
    """Delete a job. Compacts the 'Transcode Next' queue if it was in it."""
    with db_conn() as conn:
        # Check if job was in 'Transcode Next'
        cur = conn.execute("SELECT status, transcode_next_position FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            return False
        
        status, pos = row["status"], row["transcode_next_position"]
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        
        # If pending and in transcode next, close the gap
        if status == 'pending' and pos is not None:
            conn.execute("""
            UPDATE jobs
            SET transcode_next_position = transcode_next_position - 1
            WHERE status = 'pending' AND transcode_next_position > ?
            """, (pos,))
        return True

# Queue Operations & SQLite Queries
def add_to_transcode_next(job_id: int) -> bool:
    """Move job from normal queue to the end of the Transcode Next queue."""
    with db_conn() as conn:
        # Verify job is pending and not already in Transcode Next
        cur = conn.execute("SELECT status, transcode_next_position FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row or row["status"] != "pending" or row["transcode_next_position"] is not None:
            return False
            
        # Determine next available position index (default to 0 if queue is empty)
        cur_pos = conn.execute("""
        SELECT COALESCE(MAX(transcode_next_position) + 1, 0) AS next_pos
        FROM jobs
        WHERE status = 'pending' AND transcode_next_position IS NOT NULL;
        """)
        next_pos = cur_pos.fetchone()["next_pos"]
        
        conn.execute("""
        UPDATE jobs
        SET transcode_next_position = ?
        WHERE id = ? AND status = 'pending';
        """, (next_pos, job_id))
        return True

def insert_into_transcode_next(job_id: int, target_pos: int) -> bool:
    """Insert job into Transcode Next at a specific position."""
    with db_conn() as conn:
        # Verify job is pending
        cur = conn.execute("SELECT status, transcode_next_position FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row or row["status"] != "pending":
            return False
            
        current_pos = row["transcode_next_position"]
        
        if current_pos is not None:
            # Job is already in Transcode Next queue. Run reorder logic.
            return reorder_transcode_next(job_id, current_pos, target_pos)
            
        # Shift elements at or below target down
        conn.execute("""
        UPDATE jobs
        SET transcode_next_position = transcode_next_position + 1
        WHERE status = 'pending' AND transcode_next_position >= ?;
        """, (target_pos,))
        
        # Assign target position
        conn.execute("""
        UPDATE jobs
        SET transcode_next_position = ?
        WHERE id = ? AND status = 'pending';
        """, (target_pos, job_id))
        return True

def reorder_transcode_next(job_id: int, from_pos: int, to_pos: int) -> bool:
    """Reorder Transcode Next queue positions (drag'n'drop)."""
    if from_pos == to_pos:
        return True
        
    with db_conn() as conn:
        if from_pos > to_pos:
            # Shift elements in between down to make space
            conn.execute("""
            UPDATE jobs
            SET transcode_next_position = transcode_next_position + 1
            WHERE status = 'pending'
              AND transcode_next_position >= ?
              AND transcode_next_position < ?;
            """, (to_pos, from_pos))
        else:
            # Shift elements in between up to close the gap
            conn.execute("""
            UPDATE jobs
            SET transcode_next_position = transcode_next_position - 1
            WHERE status = 'pending'
              AND transcode_next_position > ?
              AND transcode_next_position <= ?;
            """, (from_pos, to_pos))
            
        # Set new position for dragged job
        conn.execute("""
        UPDATE jobs
        SET transcode_next_position = ?
        WHERE id = ?;
        """, (to_pos, job_id))
        return True

def remove_from_transcode_next(job_id: int) -> bool:
    """Remove a job from the Transcode Next queue back to normal queue."""
    with db_conn() as conn:
        cur = conn.execute("SELECT transcode_next_position FROM jobs WHERE id = ? AND status = 'pending'", (job_id,))
        row = cur.fetchone()
        if not row or row["transcode_next_position"] is None:
            return False
            
        current_pos = row["transcode_next_position"]
        
        # Clear custom position
        conn.execute("UPDATE jobs SET transcode_next_position = NULL WHERE id = ?", (job_id,))
        
        # Close the gap
        conn.execute("""
        UPDATE jobs
        SET transcode_next_position = transcode_next_position - 1
        WHERE status = 'pending' AND transcode_next_position > ?;
        """, (current_pos,))
        return True

def start_next_job() -> Optional[Dict[str, Any]]:
    """Atomically fetch the next pending job, mark it running, and reorder queue."""
    with db_conn() as conn:
        # Get next job
        cur = conn.execute("""
        SELECT id, transcode_next_position
        FROM jobs
        WHERE status = 'pending'
        ORDER BY
          CASE WHEN transcode_next_position IS NOT NULL THEN 0 ELSE 1 END ASC,
          transcode_next_position ASC,
          priority DESC,
          created_at ASC
        LIMIT 1;
        """)
        row = cur.fetchone()
        if not row:
            return None
            
        job_id, started_pos = row["id"], row["transcode_next_position"]
        
        # Update status to running
        conn.execute("""
        UPDATE jobs
        SET status = 'running',
            started_at = CURRENT_TIMESTAMP,
            transcode_next_position = NULL
        WHERE id = ?;
        """, (job_id,))
        
        # If it was in Transcode Next, shift down remaining items to close the gap
        if started_pos is not None:
            conn.execute("""
            UPDATE jobs
            SET transcode_next_position = transcode_next_position - 1
            WHERE status = 'pending' AND transcode_next_position > ?;
            """, (started_pos,))
            
        # Return full updated job details
        cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return dict(cur.fetchone())

# Media Files Helpers
def get_media_files(parent_path: str) -> List[Dict[str, Any]]:
    """Get direct children of a folder from cached database."""
    with db_conn() as conn:
        cur = conn.execute("""
        SELECT * FROM media_files
        WHERE parent_path = ?
        ORDER BY is_dir DESC, name ASC;
        """, (parent_path,))
        return [dict(row) for row in cur.fetchall()]

def search_media_files(query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Search for files matching query in name."""
    with db_conn() as conn:
        cur = conn.execute("""
        SELECT * FROM media_files
        WHERE name LIKE ?
        ORDER BY is_dir DESC, name ASC
        LIMIT ?;
        """, (f"%{query}%", limit))
        return [dict(row) for row in cur.fetchall()]

def sync_media_files_db(discovered_files: List[Dict[str, Any]]):
    """
    Perform a complete sync:
    1. Bulk upsert (insert or replace) all discovered paths.
    2. Prune paths that no longer exist on disk.
    """
    if not discovered_files:
        # If nothing is scanned, clear the table
        with db_conn() as conn:
            conn.execute("DELETE FROM media_files;")
        return

    discovered_paths = [f["path"] for f in discovered_files]
    
    with db_conn() as conn:
        # Upsert in transactions of 1000 items
        chunk_size = 1000
        for i in range(0, len(discovered_files), chunk_size):
            chunk = discovered_files[i:i + chunk_size]
            conn.executemany("""
            INSERT OR REPLACE INTO media_files (path, name, parent_path, is_dir, size, mtime)
            VALUES (:path, :name, :parent_path, :is_dir, :size, :mtime);
            """, chunk)
            
        # Prune dead paths: select all cached paths and delete ones not in discovered_paths
        # To avoid sqlite limit on placeholders, we can do batch comparisons or query all current,
        # find set differences, and delete in chunks.
        cur = conn.execute("SELECT path FROM media_files;")
        cached_paths = {row["path"] for row in cur.fetchall()}
        dead_paths = cached_paths - set(discovered_paths)
        
        if dead_paths:
            dead_list = list(dead_paths)
            for i in range(0, len(dead_list), chunk_size):
                sub_list = dead_list[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(sub_list))
                conn.execute(f"DELETE FROM media_files WHERE path IN ({placeholders})", tuple(sub_list))
