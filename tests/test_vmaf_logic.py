import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import json
import asyncio
import threading
from unittest.mock import patch, MagicMock
from pathlib import Path
from app.main import api_tool_vmaf_compare
from app.engine import run_vmaf_comparison, transcode_video

def run_async_in_thread(coro):
    res = []
    err = []
    def target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res.append(loop.run_until_complete(coro))
        except Exception as e:
            err.append(e)
        finally:
            loop.close()
    t = threading.Thread(target=target)
    t.start()
    t.join()
    if err:
        raise err[0]
    return res[0]

@patch("subprocess.run")
def test_run_vmaf_comparison_seeking(mock_run):
    """
    Verify that run_vmaf_comparison correctly constructs the ffmpeg seeking arguments.
    """
    mock_run.return_value = MagicMock(returncode=0, stderr="VMAF score: 95.0")
    
    # Case 1: No dist_start_time specified (defaults to 0.0)
    run_vmaf_comparison(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=123.45,
        duration=10.0,
        use_mpdecimate=False,
        model_type="1080p",
        video_width=1920,
        video_height=1080
    )
    args, _ = mock_run.call_args
    cmd = args[0]
    
    ref_idx = cmd.index(str(Path("ref.mp4")))
    # Symmetrical seeking format: -ss start_time -t duration -i ref_path
    assert cmd[ref_idx - 1] == "-i"
    assert cmd[ref_idx - 2] == "10.000"
    assert cmd[ref_idx - 3] == "-t"
    assert cmd[ref_idx - 4] == "123.450"
    assert cmd[ref_idx - 5] == "-ss"
    
    dist_idx = cmd.index(str(Path("dist.mp4")))
    assert cmd[dist_idx - 1] == "-i"
    assert cmd[dist_idx - 2] == "10.000"
    assert cmd[dist_idx - 3] == "-t"
    assert cmd[dist_idx - 4] == "0.000"
    assert cmd[dist_idx - 5] == "-ss"
    
    # Case 2: Symmetrical dist_start_time specified
    run_vmaf_comparison(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=123.45,
        duration=10.0,
        use_mpdecimate=False,
        model_type="1080p",
        video_width=1920,
        video_height=1080,
        dist_start_time=123.45
    )
    args, _ = mock_run.call_args
    cmd = args[0]
    
    dist_idx = cmd.index(str(Path("dist.mp4")))
    assert cmd[dist_idx - 1] == "-i"
    assert cmd[dist_idx - 2] == "10.000"
    assert cmd[dist_idx - 3] == "-t"
    assert cmd[dist_idx - 4] == "123.450"
    assert cmd[dist_idx - 5] == "-ss"


# Symmetrical os.stat mock to avoid breaking pathlib directory creation/is_dir logic
orig_os_stat = os.stat
def os_stat_side_effect(path, *args, **kwargs):
    path_str = str(path)
    if "input.mp4" in path_str or "output.mp4" in path_str:
        res = MagicMock()
        res.st_size = 1000
        res.st_mode = 33188
        return res
    return orig_os_stat(path, *args, **kwargs)


@patch("app.engine.run_vmaf_comparison")
@patch("app.engine.probe_video")
@patch("subprocess.Popen")
@patch("app.engine.update_job")
@patch("app.engine.get_job")
@patch("os.stat", side_effect=os_stat_side_effect)
def test_transcode_video_vmaf_skip(mock_stat, mock_get_job, mock_update, mock_popen, mock_probe, mock_vmaf_compare):
    """
    Verify that if calculate_final_vmaf is set to False, VMAF calculation is skipped.
    """
    mock_process = MagicMock()
    mock_process.wait.return_value = 0
    mock_process.stdout.readline.return_value = ""
    mock_popen.return_value = mock_process
    mock_probe.return_value = {"fps": 30.0, "nb_frames": 300, "duration": 10.0, "width": 1920, "height": 1080}
    
    mock_get_job.return_value = {
        "id": 999,
        "input_path": "input.mp4",
        "output_path": "output.mp4",
        "preset_config": json.dumps({
            "video": {"codec": "libx264", "preset": "fast", "pixel_format": "yuv420p"},
            "optimization": {
                "calculate_final_vmaf": False,
                "final_vmaf_mode": "sample",
                "vmaf_model": "1080p",
                "duplicate_frame_detection": False
            },
            "audio": {},
            "subtitles": {},
            "output": {}
        })
    }
    
    transcode_video(job_id=999)
    mock_vmaf_compare.assert_not_called()


@patch("app.engine.run_vmaf_comparison")
@patch("app.engine.probe_video")
@patch("subprocess.Popen")
@patch("app.engine.update_job")
@patch("app.engine.get_job")
@patch("os.stat", side_effect=os_stat_side_effect)
def test_transcode_video_vmaf_modes(mock_stat, mock_get_job, mock_update, mock_popen, mock_probe, mock_vmaf_compare):
    """
    Verify that if calculate_final_vmaf is True, VMAF calculation respects snippet vs full modes.
    """
    mock_process = MagicMock()
    mock_process.wait.return_value = 0
    mock_process.stdout.readline.return_value = ""
    mock_popen.return_value = mock_process
    mock_probe.return_value = {"fps": 30.0, "nb_frames": 6000, "duration": 200.0, "width": 1920, "height": 1080}
    
    # Case 1: Snippet mode
    mock_get_job.return_value = {
        "id": 999,
        "input_path": "input.mp4",
        "output_path": "output.mp4",
        "preset_config": json.dumps({
            "video": {"codec": "libx264", "preset": "fast", "pixel_format": "yuv420p"},
            "optimization": {
                "calculate_final_vmaf": True,
                "final_vmaf_mode": "sample",
                "vmaf_model": "1080p",
                "duplicate_frame_detection": False
            },
            "audio": {},
            "subtitles": {},
            "output": {}
        })
    }
    
    transcode_video(job_id=999)
    mock_vmaf_compare.assert_called_once()
    _, kwargs = mock_vmaf_compare.call_args
    assert kwargs["start_time"] == pytest.approx(70.0)
    assert kwargs["duration"] == 60.0
    assert kwargs["dist_start_time"] == pytest.approx(70.0)
    
    mock_vmaf_compare.reset_mock()
    
    # Case 2: Full video mode
    mock_get_job.return_value = {
        "id": 999,
        "input_path": "input.mp4",
        "output_path": "output.mp4",
        "preset_config": json.dumps({
            "video": {"codec": "libx264", "preset": "fast", "pixel_format": "yuv420p"},
            "optimization": {
                "calculate_final_vmaf": True,
                "final_vmaf_mode": "full",
                "vmaf_model": "1080p",
                "duplicate_frame_detection": False
            },
            "audio": {},
            "subtitles": {},
            "output": {}
        })
    }
    transcode_video(job_id=999)
    mock_vmaf_compare.assert_called_once()
    _, kwargs = mock_vmaf_compare.call_args
    assert kwargs["start_time"] == 0.0
    assert kwargs["duration"] == 200.0
    assert kwargs["dist_start_time"] == 0.0


@patch("app.main.run_vmaf_comparison")
@patch("app.main.probe_video")
@patch("app.main.Path.exists")
@patch("app.main.templates.TemplateResponse")
def test_api_vmaf_compare_endpoint_seeking(mock_tmpl, mock_exists, mock_probe, mock_vmaf_compare):
    """
    Verify that the VMAF comparison tool endpoint correctly handles segment and sampled seeking.
    """
    mock_exists.return_value = True
    mock_probe.return_value = {"duration": 100.0, "width": 1920, "height": 1080}
    mock_vmaf_compare.return_value = 95.0
    mock_tmpl.return_value = MagicMock()
    mock_request = MagicMock()
    
    # Case 1: Segment mode
    run_async_in_thread(api_tool_vmaf_compare(
        request=mock_request,
        ref_path="ref.mp4",
        dist_path="dist.mp4",
        vmaf_model="1080p",
        compare_mode="segment",
        start_time=45.0,
        duration=15.0,
        dedup=False
    ))
    
    mock_vmaf_compare.assert_called_once_with(
        ref_path=Path("ref.mp4"),
        dist_path=Path("dist.mp4"),
        start_time=45.0,
        duration=15.0,
        use_mpdecimate=False,
        model_type="1080p",
        video_width=1920,
        video_height=1080,
        dist_start_time=45.0
    )
    
    mock_vmaf_compare.reset_mock()
    
    # Case 2: Sampled mode
    run_async_in_thread(api_tool_vmaf_compare(
        request=mock_request,
        ref_path="ref.mp4",
        dist_path="dist.mp4",
        vmaf_model="1080p",
        compare_mode="sampled",
        start_time=0.0,
        duration=10.0,
        dedup=False
    ))
    
    assert mock_vmaf_compare.call_count == 3
    calls = mock_vmaf_compare.call_args_list
    
    # Verify first sampled checkpoint
    _, kwargs1 = calls[0]
    assert kwargs1["start_time"] == 20.0
    assert kwargs1["dist_start_time"] == 20.0
    
    # Verify second sampled checkpoint
    _, kwargs2 = calls[1]
    assert kwargs2["start_time"] == 50.0
    assert kwargs2["dist_start_time"] == 50.0
    
    # Verify third sampled checkpoint
    _, kwargs3 = calls[2]
    assert kwargs3["start_time"] == 80.0
    assert kwargs3["dist_start_time"] == 80.0
