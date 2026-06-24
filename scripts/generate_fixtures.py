import os
import subprocess
from pathlib import Path

def generate_fixtures():
    # Define paths
    project_root = Path(__file__).resolve().parent.parent
    fixtures_dir = project_root / "tests" / "fixtures" / "media"
    
    # Ensure directory exists
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating test fixtures in: {fixtures_dir}")

    # 1. Standard Test Video (2 seconds, 30fps, test pattern)
    standard_test_path = fixtures_dir / "standard_test.mp4"
    if not standard_test_path.exists():
        print("Generating standard_test.mp4...")
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=30",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            str(standard_test_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("standard_test.mp4 already exists.")

    # 2. Duplicates Video (2 seconds, 30fps, with intentional duplicated frames)
    # We use the tblend filter with 'all_mode=average' or similar to create motion, then drop and duplicate frames to create stutter
    duplicates_path = fixtures_dir / "duplicates.mp4"
    if not duplicates_path.exists():
        print("Generating duplicates.mp4...")
        # Create a 2s video where half the frames are explicitly duplicated (e.g., dropping every 2nd frame and repeating the previous)
        # We can achieve this by generating at 15fps and then changing output to 30fps without interpolation (it will duplicate frames)
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=15",
            "-r", "30", # Force 30fps output, duplicating the 15fps frames
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            str(duplicates_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("duplicates.mp4 already exists.")

    # 3. VMAF Distorted Video (2 seconds, 30fps, heavily compressed version of standard_test)
    vmaf_distorted_path = fixtures_dir / "vmaf_distorted.mp4"
    if not vmaf_distorted_path.exists():
        print("Generating vmaf_distorted.mp4...")
        # Take the standard test and compress it terribly
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(standard_test_path),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "45", # High CRF for distortion
            str(vmaf_distorted_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("vmaf_distorted.mp4 already exists.")

    print("\n[OK] All fixtures generated successfully!")

if __name__ == "__main__":
    generate_fixtures()
