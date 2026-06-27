import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine import get_vmaf_model_filter_param

def test_vmaf_model_selection():
    # Test explicitly selected models (ignore resolution)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("1080p", 3840, 2160)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("4k_far", 3840, 2160)
    assert "vmaf_4k_v0.6.1" in get_vmaf_model_filter_param("4k_near", 1920, 1080)
    
    # Test Auto Near logic
    # 1080p input -> should pick 1080p model
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_near", 1920, 1080)
    # 4K input -> should pick 4k_near model
    assert "vmaf_4k_v0.6.1" in get_vmaf_model_filter_param("auto_near", 3840, 2160)
    
    # Test Auto Far logic
    # 1080p input -> should pick 1080p model
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_far", 1920, 1080)
    # 4K input -> should pick 4k_far (which is functionally equivalent to the 1080p model file, vmaf_v0.6.1)
    assert "vmaf_4k" not in get_vmaf_model_filter_param("auto_far", 3840, 2160)

from unittest.mock import patch, MagicMock
from pathlib import Path
from app.engine import run_vmaf_comparison

@patch("subprocess.run")
def test_vmaf_upscaling_filter(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stderr="VMAF score: 95.0")
    
    # Case 1: 720p input resolution compared using 1080p model -> must upscale to 1920:1080
    run_vmaf_comparison(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=0.0,
        duration=5.0,
        use_mpdecimate=False,
        model_type="1080p",
        video_width=1280,
        video_height=720
    )
    args, kwargs = mock_run.call_args
    cmd = args[0]
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=1920:1080:flags=bicubic" in filter_complex
    assert "scale2ref" not in filter_complex

    # Case 2: 1080p input resolution compared using 4k_near model -> must upscale to 3840:2160
    run_vmaf_comparison(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=0.0,
        duration=5.0,
        use_mpdecimate=False,
        model_type="4k_near",
        video_width=1920,
        video_height=1080
    )
    args, kwargs = mock_run.call_args
    cmd = args[0]
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=3840:2160:flags=bicubic" in filter_complex
    assert "scale2ref" not in filter_complex

    # Case 3: 1080p input resolution compared using 1080p model (matching resolution) -> uses scale2ref
    run_vmaf_comparison(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=0.0,
        duration=5.0,
        use_mpdecimate=False,
        model_type="1080p",
        video_width=1920,
        video_height=1080
    )
    args, kwargs = mock_run.call_args
    cmd = args[0]
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "scale2ref" in filter_complex
    assert "scale=" not in filter_complex
