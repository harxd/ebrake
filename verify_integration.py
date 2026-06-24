import os
import sys
import shutil
import tempfile
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime

# 1. Setup Sandbox Environment before importing app modules
sandbox_dir = Path(tempfile.mkdtemp(prefix="ebrake_test_")).resolve()
appdata_dir = sandbox_dir / "appdata"
media_dir = sandbox_dir / "media"

os.environ["EBRAKE_APPDATA_DIR"] = str(appdata_dir)
os.environ["EBRAKE_MEDIA_DIR"] = str(media_dir)

# Add current directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

# Import app modules now that environment is overridden
from app.config import init_directories, DB_PATH
from app.database import (
    init_db, get_jobs, get_job, create_job, delete_job,
    get_setting, set_setting, add_to_transcode_next, start_next_job
)
from app.profiles import init_profiles, get_profile
from app.scanner import run_library_sync
from app.engine import (
    transcode_video, run_dedup_dryrun, run_vmaf_search, probe_video,
    start_worker, pause_queue, resume_queue, queue_paused, run_vmaf_comparison
)
from app.main import app, api_media_search, api_save_settings

# Track overall test success
tests_passed = True

def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def generate_test_assets():
    print("Generating synthetic video with duplicate frames and soft subtitles...")
    
    # Ensure media directory exists
    media_dir.mkdir(parents=True, exist_ok=True)
    
    video_mp4 = media_dir / "temp_input.mp4"
    subs_srt = media_dir / "temp_subs.srt"
    input_mkv = media_dir / "temp_input.mkv"
    
    # 1. Create a 5-second 25fps video from a 5fps source (each frame duplicated 5 times)
    cmd_gen_video = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=5",
        "-vf", "fps=25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_mp4)
    ]
    subprocess.run(cmd_gen_video, capture_output=True, check=True)
    print(f"[OK] Generated raw test video: {video_mp4.name}")
    
    # 2. Create a simple subtitle SRT track
    srt_content = """1
00:00:01,000 --> 00:00:04,000
Test Subtitle Overlay Line
"""
    with open(subs_srt, "w") as f:
        f.write(srt_content)
    print(f"[OK] Generated raw subtitles: {subs_srt.name}")
    
    # 3. Merge them into a Matroska (.mkv) container
    cmd_merge = [
        "ffmpeg", "-y",
        "-i", str(video_mp4),
        "-i", str(subs_srt),
        "-map", "0:v:0", "-map", "1:s:0",
        "-c:v", "copy", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng",
        str(input_mkv)
    ]
    subprocess.run(cmd_merge, capture_output=True, check=True)
    print(f"[OK] Merged assets into container: {input_mkv.name}")
    
    # Remove raw intermediates
    if video_mp4.exists():
        video_mp4.unlink()
    if subs_srt.exists():
        subs_srt.unlink()
        
    return input_mkv

def check_ffmpeg_vmaf():
    """Checks if libvmaf filter is available in host's ffmpeg."""
    try:
        res = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        return "libvmaf" in res.stdout
    except Exception:
        return False

def test_setup_and_init():
    print_section("Phase 1: Setup and Directory Initialization")
    
    print("Testing sandbox directories creation...")
    init_directories()
    assert appdata_dir.exists(), "Appdata directory not found!"
    assert media_dir.exists(), "Media directory not found!"
    
    print("Testing DB initialization...")
    init_db()
    assert DB_PATH.exists(), "SQLite DB file not created!"
    
    print("Testing settings read/write...")
    set_setting("privacy_mode_enabled", True)
    assert get_setting("privacy_mode_enabled") is True, "Settings storage check failed!"
    
    print("Testing profile preset generation...")
    init_profiles()
    profile = get_profile("Default", "AV1 VMAF Auto-CRF")
    assert profile is not None, "Failed to load default profiles!"
    assert profile["video"]["codec"] == "libsvtav1", "Profile codec parsing error!"
    print("[SUCCESS] Phase 1 checks passed successfully.")

def test_queues_and_reordering():
    print_section("Phase 2: Queue & Priority Reordering")
    
    # Create jobs with priority
    job_low = create_job({
        "status": "pending",
        "input_path": str(media_dir / "dummy_low.mp4"),
        "output_path": str(media_dir / "dummy_low_out.mkv"),
        "priority": 1,
        "category": "Default",
        "preset": "H264 1080p Fast",
        "subtitle_mode": "none"
    })
    
    job_high = create_job({
        "status": "pending",
        "input_path": str(media_dir / "dummy_high.mp4"),
        "output_path": str(media_dir / "dummy_high_out.mkv"),
        "priority": 10,
        "category": "Default",
        "preset": "H264 1080p Fast",
        "subtitle_mode": "none"
    })
    
    # Assert higher priority comes first
    pending = get_jobs("pending")
    assert pending[0]["id"] == job_high, "Priority sorting failed!"
    print("[OK] Priority sorting (priority DESC) works.")
    
    # Promote low priority to 'Transcode Next'
    add_to_transcode_next(job_low)
    pending = get_jobs("pending")
    assert pending[0]["id"] == job_low, "Transcode Next scheduling failed!"
    print("[OK] Transcode Next overrides priority ordering.")
    
    # Clean up jobs
    delete_job(job_low)
    delete_job(job_high)
    print("[SUCCESS] Phase 2 checks passed successfully.")

def test_transcode_pipeline(input_file: Path):
    print_section("Phase 3: E2E Video Transcoding Pipeline")
    
    # Ensure background worker doesn't run during sync test
    pause_queue()
    
    # 1. Test standard H264 transcode
    print("Testing basic H.264 transcoding...")
    h264_profile = get_profile("Default", "H264 1080p Fast")
    
    job_h264 = create_job({
        "status": "pending",
        "input_path": str(input_file),
        "output_path": str(media_dir / "out_basic.mp4"),
        "priority": 0,
        "category": "Default",
        "preset": "H264 1080p Fast",
        "preset_config": json.dumps(h264_profile),
        "subtitle_mode": "none"
    })
    
    # Process job directly
    transcode_video(job_h264)
    
    # Assert completion
    job_info = get_job(job_h264)
    assert job_info["status"] == "completed", f"Transcode failed: {job_info['error']}"
    assert Path(job_info["output_path"]).exists(), "Output file not found on disk!"
    print("[OK] H.264 transcode completed successfully.")
    
    # 2. Test Duplicate Frame Detection
    print("\nTesting Duplicate Frame Detection (mpdecimate)...")
    dedup_profile = get_profile("Default", "AV1 VMAF Auto-CRF")
    dedup_profile["optimization"]["duplicate_frame_detection"] = True
    dedup_profile["optimization"]["target_vmaf"] = 0.0  # disable VMAF for this run
    dedup_profile["video"]["crf"] = 28 # fixed crf
    
    job_dedup = create_job({
        "status": "pending",
        "input_path": str(input_file),
        "output_path": str(media_dir / "out_dedup.mkv"),
        "priority": 0,
        "category": "Default",
        "preset": "AV1 VMAF Auto-CRF",
        "preset_config": json.dumps(dedup_profile),
        "subtitle_mode": "none"
    })
    
    transcode_video(job_dedup)
    
    job_info = get_job(job_dedup)
    assert job_info["status"] == "completed", f"Deduplication transcode failed: {job_info['error']}"
    
    # Assert frame drop metric (25fps source decimated to ~5fps)
    source_fps = job_info["source_fps"]
    unduplicated_fps = job_info["unduplicated_fps"]
    print(f"Source FPS: {source_fps}, Unduplicated FPS: {unduplicated_fps:.2f}")
    assert unduplicated_fps < source_fps * 0.5, "Duplicate frame detection did not drop enough frames!"
    print("[OK] Duplicate frame detection correctly registered metrics.")
    
    # 3. Test VMAF Auto-CRF Search
    has_vmaf = check_ffmpeg_vmaf()
    if has_vmaf:
        print("\nTesting VMAF Auto-CRF Search...")
        vmaf_profile = get_profile("Default", "AV1 VMAF Auto-CRF")
        vmaf_profile["optimization"]["target_vmaf"] = 93.0
        vmaf_profile["optimization"]["vmaf_search_range"] = [22, 32]
        vmaf_profile["optimization"]["duplicate_frame_detection"] = False
        
        job_vmaf = create_job({
            "status": "pending",
            "input_path": str(input_file),
            "output_path": str(media_dir / "out_vmaf.mkv"),
            "priority": 0,
            "category": "Default",
            "preset": "AV1 VMAF Auto-CRF",
            "preset_config": json.dumps(vmaf_profile),
            "subtitle_mode": "none"
        })
        
        transcode_video(job_vmaf)
        
        job_info = get_job(job_vmaf)
        assert job_info["status"] == "completed", f"VMAF Search transcode failed: {job_info['error']}"
        assert job_info["selected_crf"] is not None, "Auto-CRF search did not select a CRF!"
        assert job_info["measured_vmaf"] is not None, "Final transcode did not measure output VMAF!"
        print(f"Selected CRF: {job_info['selected_crf']}, Measured VMAF: {job_info['measured_vmaf']:.2f}")
        print("[OK] VMAF Auto-CRF optimization successfully converged.")
    else:
        print("\n[WARNING] FFmpeg on host does not have libvmaf filter enabled. Skipping Auto-CRF test.")

    # 4. Test Subtitle Burn-In
    print("\nTesting Subtitle Burn-In...")
    sub_profile = get_profile("Default", "H264 1080p Fast")
    sub_profile["subtitles"]["mode"] = "burn-in"
    sub_profile["subtitles"]["burn_in_track_select"] = "default"
    
    job_subs = create_job({
        "status": "pending",
        "input_path": str(input_file),
        "output_path": str(media_dir / "out_sub_burn.mp4"),
        "priority": 0,
        "category": "Default",
        "preset": "H264 1080p Fast",
        "preset_config": json.dumps(sub_profile),
        "subtitle_mode": "burn-in"
    })
    
    transcode_video(job_subs)
    
    job_info = get_job(job_subs)
    assert job_info["status"] == "completed", f"Subtitle burn-in transcode failed: {job_info['error']}"
    assert job_info["selected_subtitle_track"] is not None, "Failed to map subtitle track index!"
    print(f"[OK] Subtitle burn-in mapping identified track: {job_info['selected_subtitle_track']}")

    print("[SUCCESS] Phase 3 checks passed successfully.")

def test_standalone_tools(input_file: Path):
    print_section("Phase 4: Standalone Tools Dry-Runs")
    
    print("Testing standalone FPS Deduplication dryrun...")
    results = run_dedup_dryrun(input_file)
    assert results["dropped_frames"] > 0, "Deduplication dry-run found no duplicate frames!"
    assert results["unduplicated_fps"] < results["source_fps"], "Deduplication dry-run FPS did not drop!"
    print(f"Dry-run: source frames {results['total_frames']}, unique {results['unique_frames']}, space saved: {results['saved_space_pct']:.1f}%")
    print("[OK] Standalone FPS Deduplication calculator works.")
    
    has_vmaf = check_ffmpeg_vmaf()
    if has_vmaf:
        print("\nTesting standalone VMAF Search dryrun with custom model...")
        crf = run_vmaf_search(
            input_path=input_file,
            codec="libx264",
            preset="faster",
            pix_fmt="yuv420p",
            filters=None,
            target_vmaf=95.0,
            crf_range=(20, 30),
            duration=5.0,
            use_mpdecimate=False,
            model_type="4k_near"
        )
        assert 20 <= crf <= 30, f"VMAF Search dry-run returned out-of-bounds CRF: {crf}"
        print(f"Selected CRF for 95.0 VMAF (4K near model): {crf}")
        print("[OK] Standalone VMAF optimizer works.")
        
        print("\nTesting VMAF Comparison with resolution scaling...")
        downscaled_file = media_dir / "temp_input_downscaled.mp4"
        cmd_downscale = [
            "ffmpeg", "-y",
            "-i", str(input_file),
            "-vf", "scale=160:120",
            "-c:v", "libx264", "-an", "-sn",
            str(downscaled_file)
        ]
        subprocess.run(cmd_downscale, capture_output=True, check=True)
        
        # Calculate VMAF score between 320x240 source and 160x120 downscaled
        score = run_vmaf_comparison(
            ref_path=input_file,
            dist_path=downscaled_file,
            start_time=0.0,
            duration=2.0,
            use_mpdecimate=False,
            model_type="1080p"
        )
        assert score > 0.0, "VMAF score on scaled video should be positive!"
        print(f"VMAF score with automatic resolution scaling: {score:.2f}")
        
        if downscaled_file.exists():
            downscaled_file.unlink()
    else:
        print("\n[WARNING] FFmpeg lacks libvmaf support. Skipping Standalone VMAF dryrun test.")
        
    print("[SUCCESS] Phase 4 checks passed successfully.")

class MockRequest:
    def __init__(self, is_htmx=True):
        self.headers = {"HX-Request": "true" if is_htmx else "false"}

async def test_non_video_endpoints():
    print_section("Phase 5: Non-Video Web APIs")
    
    print("Simulating HTTP Settings save...")
    # Mock FastAPI request call to settings endpoint
    req = MockRequest(is_htmx=True)
    res = await api_save_settings(req, recovery_action="auto_restart", privacy_mode=True)
    
    # Assert status values got updated in settings DB
    assert get_setting("on_startup_orphaned_job_action") == "auto_restart", "Settings did not persist!"
    assert get_setting("privacy_mode_enabled") is True, "Settings did not persist!"
    print("[OK] Settings update endpoint verified.")
    
    print("\nSimulating HTTP File Browser search...")
    # Trigger scanner to update search db cache
    run_library_sync()
    
    req = MockRequest(is_htmx=True)
    res_search = await api_media_search(req, q="temp")
    res_html = res_search.body.decode()
    
    # Verify that the generated test file path matches in search results snippet
    assert "temp_input.mkv" in res_html, "Search API failed to return cached search hits!"
    print("[OK] Cached search DB queries and rendering verified.")
    
    print("\nSimulating HTTP Media Sync endpoints...")
    from app.main import api_media_sync, api_media_sync_status, api_media_sync_reset
    from fastapi import BackgroundTasks
    
    # 1. Trigger sync
    bg_tasks = BackgroundTasks()
    res_sync = await api_media_sync(req, background_tasks=bg_tasks)
    assert "Updating" in res_sync, "Sync initiation response HTML mismatch!"
    
    # 2. Check status (while syncing or finished)
    res_status = await api_media_sync_status(req)
    assert ("Updating" in res_status or "Sync successful" in res_status), "Sync status response HTML mismatch!"
    
    # 3. Reset sync button
    res_reset = await api_media_sync_reset(req)
    assert "Update search db" in res_reset, "Sync reset response HTML mismatch!"
    print("[OK] Media sync, status polling, and reset endpoints verified.")
    
    print("[SUCCESS] Phase 5 checks passed successfully.")

def run_tests():
    global tests_passed
    try:
        # Step 1: Pre-tests setup
        input_mkv = generate_test_assets()
        
        # Step 2: Phase runs
        test_setup_and_init()
        test_queues_and_reordering()
        test_transcode_pipeline(input_mkv)
        test_standalone_tools(input_mkv)
        
        # Async endpoint checks require event loop
        import asyncio
        asyncio.run(test_non_video_endpoints())
        
        print("\n" + "=" * 60)
        print(" INTEGRATION VERIFICATION COMPLETED: ALL PHASES PASSED ".center(60, "*"))
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n[FAIL] Assertion Error: {e}", file=sys.stderr)
        tests_passed = False
    except Exception as e:
        print(f"\n[FAIL] Unexpected Exception: {e}", file=sys.stderr)
        tests_passed = False
    finally:
        # Cleanup Sandbox
        print("\nCleaning up sandbox environments...")
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
        print("Cleanup done.")
        
        if not tests_passed:
            sys.exit(1)

if __name__ == "__main__":
    print("=== ebrake E2E Integration Test Suite ===")
    run_tests()
