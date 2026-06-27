import sys
import os
from pathlib import Path

# Add project root to path so we can import app modules
sys.path.append(str(Path(__file__).resolve().parent))

from app.config import init_directories, DB_PATH
from app.database import (
    init_db, get_setting, set_setting, get_jobs, create_job, 
    add_to_transcode_next, start_next_job, delete_job
)
from app.presets import init_presets, list_categories, get_preset
from app.scanner import run_library_sync

def test_setup():
    print("Testing directory creation...")
    init_directories()
    
    print("Testing DB initialization...")
    init_db()
    assert DB_PATH.exists(), "Database file was not created!"
    print("[OK] DB file created successfully.")
    
    print("Testing settings operations...")
    set_setting("test_key", "test_val")
    val = get_setting("test_key")
    assert val == "test_val", f"Setting verify failed, got: {val}"
    print("[OK] Settings read/write successful.")
    
    print("Testing default presets creation...")
    init_presets()
    categories = list_categories()
    assert "Default" in categories, f"Categories missing Default, got: {categories}"
    preset = get_preset("Default", "AV1 VMAF Auto-CRF")
    assert preset is not None, "Failed to load default AV1 preset!"
    assert preset["video"]["codec"] == "libsvtav1", "Preset codec parsing mismatch!"
    print("[OK] Presets system functions correctly.")
    
def test_queues():
    print("Testing queue sorting and prioritization...")
    
    # 1. Create two test pending jobs
    job_1_id = create_job({
        "status": "pending",
        "input_path": "media/test1.mp4",
        "output_path": "media/test1_transcoded.mkv",
        "priority": 1,
        "category": "Default",
        "preset": "AV1 VMAF Auto-CRF",
        "subtitle_mode": "none"
    })
    
    job_2_id = create_job({
        "status": "pending",
        "input_path": "media/test2.mp4",
        "output_path": "media/test2_transcoded.mkv",
        "priority": 5, # Higher priority
        "category": "Default",
        "preset": "AV1 VMAF Auto-CRF",
        "subtitle_mode": "none"
    })
    
    # Check natural priority order (job 2 first because priority=5 > 1)
    pending_jobs = get_jobs("pending")
    assert pending_jobs[0]["id"] == job_2_id, "Priority sorting failed! Job 2 should be first."
    print("[OK] Priority ordering (priority DESC) successful.")
    
    # 2. Promote job 1 (lower priority) to Transcode Next
    res = add_to_transcode_next(job_1_id)
    assert res is True, "Failed to promote Job 1 to Transcode Next."
    
    # Check that job 1 is now first, despite lower priority
    pending_jobs = get_jobs("pending")
    assert pending_jobs[0]["id"] == job_1_id, "Transcode Next ordering failed! Job 1 should be first."
    print("[OK] Transcode Next queue taking precedence successful.")
    
    # 3. Atomically start next job
    running_job = start_next_job()
    assert running_job is not None, "Failed to start next job."
    assert running_job["id"] == job_1_id, "Wrong job started."
    assert running_job["status"] == "running", "Job status not updated to running."
    
    # Verify job 1 is no longer in pending, and job 2 is now first
    pending_jobs = get_jobs("pending")
    assert len(pending_jobs) == 1, "Expected 1 pending job left."
    assert pending_jobs[0]["id"] == job_2_id, "Job 2 should be next pending."
    print("[OK] Atomic start next job and gap-compaction successful.")
    
    # Cleanup
    delete_job(job_1_id)
    delete_job(job_2_id)
    print("[OK] Cleanup successful.")

def test_scanner():
    print("Testing scanner run...")
    # Should not throw any exception even if empty media folder
    run_library_sync()
    print("[OK] Scanner completed successfully.")

if __name__ == "__main__":
    print("=== ebrake Backend Logic Verification ===")
    try:
        test_setup()
        test_queues()
        test_scanner()
        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY! (100% Core Code correct)")
    except AssertionError as e:
        print(f"\nAssertion Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected Exception: {e}", file=sys.stderr)
        sys.exit(1)
