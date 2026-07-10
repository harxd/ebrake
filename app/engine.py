import os
import re
import sys
import json
import time
import shutil
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.config import TEMP_DIR, MEDIA_DIR
from app.database import (
    get_job, update_job, get_jobs, db_conn, get_setting, set_setting
)

logger = logging.getLogger(__name__)

# Global thread state
worker_thread: Optional[threading.Thread] = None
worker_lock = threading.Lock()
running_job_process: Optional[subprocess.Popen] = None
running_job_id: Optional[int] = None
queue_paused: bool = False

def is_queue_paused() -> bool:
    """Check if the queue is paused."""
    return queue_paused

# Live progress tracking
# Format: { job_id: { "progress": float, "fps": float, "speed": str, "eta": str, "ffmpeg_pid": int } }
running_progress: Dict[int, Dict[str, Any]] = {}
progress_lock = threading.Lock()

def get_running_progress(job_id: int) -> Optional[Dict[str, Any]]:
    """Thread-safe getter for live transcode progress."""
    with progress_lock:
        return running_progress.get(job_id)

def set_running_progress(job_id: int, data: Dict[str, Any]):
    """Thread-safe setter for live transcode progress."""
    with progress_lock:
        running_progress[job_id] = data

def clear_running_progress(job_id: int):
    """Thread-safe cleanup for live transcode progress."""
    with progress_lock:
        running_progress.pop(job_id, None)

def escape_filter_path(p: Path) -> str:
    """Escape windows file paths for use inside FFmpeg filter parameters."""
    return str(p).replace("\\", "/").replace(":", "\\:")

def probe_video(file_path: Path) -> Dict[str, Any]:
    """
    Probe a video file using ffprobe.
    Extracts duration, source FPS, and detailed subtitle tracks list.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Probe duration and FPS
    cmd_video = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,duration,nb_frames,pix_fmt,width,height",
        "-of", "json", str(file_path)
    ]
    
    # Probe subtitle tracks
    cmd_subs = [
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name,disposition=default,forced:stream_tags=language",
        "-of", "json", str(file_path)
    ]

    try:
        # Run video streams probe
        res_video = subprocess.run(cmd_video, capture_output=True, text=True, check=True)
        data_video = json.loads(res_video.stdout)
        
        # Run subtitles probe
        res_subs = subprocess.run(cmd_subs, capture_output=True, text=True, check=True)
        data_subs = json.loads(res_subs.stdout)
    except Exception as e:
        logger.error(f"Failed to probe file {file_path}: {e}")
        raise RuntimeError(f"Probing failed: {e}")

    # Parse video stream data
    v_stream = data_video.get("streams", [{}])[0]
    duration_str = v_stream.get("duration")
    
    # Fallback duration probe (sometimes containers hide it in formats)
    if not duration_str or duration_str == "N/A":
        cmd_format = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(file_path)
        ]
        res_format = subprocess.run(cmd_format, capture_output=True, text=True, check=True)
        data_format = json.loads(res_format.stdout)
        duration_str = data_format.get("format", {}).get("duration", "0")
        
    duration = float(duration_str) if duration_str else 0.0
    
    # Parse FPS
    fps_val = 0.0
    fps_str = v_stream.get("avg_frame_rate", "0/0")
    if "/" in fps_str:
        num, den = map(float, fps_str.split("/"))
        if den > 0:
            fps_val = num / den
    else:
        fps_val = float(fps_str)
        
    nb_frames = int(v_stream.get("nb_frames")) if v_stream.get("nb_frames") else 0
    pix_fmt = v_stream.get("pix_fmt", "yuv420p")
    width = int(v_stream.get("width")) if v_stream.get("width") else 1920
    height = int(v_stream.get("height")) if v_stream.get("height") else 1080

    # Parse subtitle tracks data
    sub_tracks = []
    for s_idx, stream in enumerate(data_subs.get("streams", [])):
        disposition = stream.get("disposition", {})
        tags = stream.get("tags", {})
        sub_tracks.append({
            "index": stream.get("index"),
            "track_id": s_idx, # 0-indexed subtitle count
            "codec": stream.get("codec_name"),
            "language": tags.get("language", "und"),
            "is_default": bool(disposition.get("default", 0)),
            "is_forced": bool(disposition.get("forced", 0))
        })

    return {
        "duration": duration,
        "fps": fps_val,
        "nb_frames": nb_frames,
        "pix_fmt": pix_fmt,
        "width": width,
        "height": height,
        "subtitles": sub_tracks
    }

def run_dedup_dryrun(file_path: Path) -> Dict[str, Any]:
    """
    Runs FPS Deduplication Dry-Run.
    Calculates duplicate frame metrics without writing a permanent output file.
    Uses temporal sampling for longer videos to optimize performance.
    """
    metadata = probe_video(file_path)
    duration = metadata["duration"]
    source_fps = metadata["fps"]
    total_frames = metadata["nb_frames"]
    
    if total_frames <= 0 and duration > 0 and source_fps > 0:
        total_frames = int(duration * source_fps)

    # Threshold for full scan: 180 seconds (3 minutes)
    if duration <= 180.0:
        # Run full scan (use strict parameters)
        cmd_dedup = [
            "ffmpeg", "-y", "-i", str(file_path),
            "-vf", "mpdecimate=max=0:hi=64:lo=64:frac=0.001", "-f", "null", "-"
        ]
        p_dedup = subprocess.run(cmd_dedup, capture_output=True, text=True)
        
        # Unique frames count
        unique_matches = re.findall(r"frame=\s*(\d+)", p_dedup.stderr)
        unique_frames = int(unique_matches[-1]) if unique_matches else total_frames
        dropped_frames = total_frames - unique_frames
    else:
        # Run sampled scan
        num_segments = 15
        segment_duration = 15.0
        
        # Distribute segments evenly in the middle 70% of the video
        start_min = duration * 0.15
        start_max = max(start_min, duration * 0.85 - segment_duration)
        
        segment_ratios = []
        
        for i in range(num_segments):
            if num_segments > 1:
                start_time = start_min + (start_max - start_min) * i / (num_segments - 1)
            else:
                start_time = (start_min + start_max) / 2.0
                
            cmd_segment = [
                "ffmpeg", "-y",
                "-ss", f"{start_time:.3f}",
                "-t", f"{segment_duration:.3f}",
                "-i", str(file_path),
                "-vf", "mpdecimate=max=0:hi=64:lo=64:frac=0.001",
                "-f", "null", "-"
            ]
            
            p_segment = subprocess.run(cmd_segment, capture_output=True, text=True)
            unique_matches = re.findall(r"frame=\s*(\d+)", p_segment.stderr)
            
            segment_expected = int(segment_duration * source_fps)
            segment_unique = int(unique_matches[-1]) if unique_matches else segment_expected
            segment_unique = min(segment_unique, segment_expected)
            
            segment_dup_ratio = (segment_expected - segment_unique) / segment_expected if segment_expected > 0 else 0.0
            segment_ratios.append(segment_dup_ratio)
            
        # Outlier rejection using trimmed mean
        segment_ratios.sort()
        # Discard the top 3 and bottom 3 segments
        trimmed_ratios = segment_ratios[3:-3]
        if trimmed_ratios:
            dup_ratio = sum(trimmed_ratios) / len(trimmed_ratios)
        else:
            dup_ratio = sum(segment_ratios) / len(segment_ratios) if segment_ratios else 0.0
            
        dropped_frames = int(dup_ratio * total_frames)
        unique_frames = total_frames - dropped_frames
        
    unduplicated_fps = unique_frames / duration if duration > 0 else source_fps
    saved_space_pct = (dropped_frames / total_frames * 100) if total_frames > 0 else 0.0
    
    return {
        "total_frames": total_frames,
        "unique_frames": unique_frames,
        "dropped_frames": dropped_frames,
        "source_fps": source_fps,
        "unduplicated_fps": unduplicated_fps,
        "saved_space_pct": saved_space_pct
    }

def get_vmaf_model_filter_param(model_type: str, width: int = 1920, height: int = 1080) -> str:
    """Resolves VMAF model path or built-in version string based on type."""
    if model_type in ("auto_near", "auto_far"):
        is_4k = (width > 1920 or height > 1080)
        if model_type == "auto_near":
            model_type = "4k_near" if is_4k else "1080p"
        else:
            model_type = "4k_far" if is_4k else "1080p"

    if model_type == "4k_near":
        path = Path("/usr/share/model/vmaf_4k_v0.6.1.json")
        if path.exists():
            return f"model='path={escape_filter_path(path)}'"
        return "model='version=vmaf_4k_v0.6.1'"
    else:  # 1080p or 4k_far
        path = Path("/usr/share/model/vmaf_v0.6.1.json")
        if path.exists():
            return f"model='path={escape_filter_path(path)}'"
        return "model='version=vmaf_v0.6.1'"

def run_vmaf_comparison(
    ref_path: Path, 
    dist_path: Path, 
    start_time: float, 
    duration: float, 
    use_mpdecimate: bool, 
    duplicate_threshold: float = 0.001,
    model_type: str = "1080p",
    video_width: int = 1920,
    video_height: int = 1080,
    dist_start_time: Optional[float] = None
) -> float:
    """
    Computes VMAF on segment samples.
    Saves JSON results and returns mean score.
    Automatically upscales distorted video to reference video resolution if needed.
    """
    log_file = TEMP_DIR / f"vmaf_{int(time.time() * 1000)}.json"
    escaped_log = escape_filter_path(log_file)
    
    model_param = get_vmaf_model_filter_param(model_type, video_width, video_height)
    
    # Determine target resolution based on the resolved model (Netflix guidelines)
    if "vmaf_4k" in model_param:
        tw, th = 3840, 2160
    else:
        tw, th = 1920, 1080
        
    # Scale streams to match target model resolution using bicubic upscaling if they differ
    filters = []
    ref_label = "[0:v]"
    dist_label = "[1:v]"
    
    if use_mpdecimate:
        filters.append(f"[0:v]mpdecimate=max=0:hi=64:lo=64:frac={duplicate_threshold}[ref_dec]")
        ref_label = "[ref_dec]"
        
    if video_width != tw or video_height != th:
        filters.append(f"{ref_label}scale={tw}:{th}:flags=bicubic[ref_scaled]")
        filters.append(f"{dist_label}scale={tw}:{th}:flags=bicubic[dist_scaled]")
        ref_label = "[ref_scaled]"
        dist_label = "[dist_scaled]"
    else:
        # Fallback to scale2ref if dimensions already match target VMAF resolution
        filters.append(f"{dist_label}{ref_label}scale2ref[dist_scaled][ref_out]")
        ref_label = "[ref_out]"
        dist_label = "[dist_scaled]"
        
    filters.append(f"{ref_label}{dist_label}libvmaf={model_param}:log_fmt=json:log_path='{escaped_log}'")
    filter_complex = ";".join(filters)
        
    d_start = dist_start_time if dist_start_time is not None else 0.0
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_time:.3f}", "-t", f"{duration:.3f}", "-i", str(ref_path),
        "-ss", f"{d_start:.3f}", "-t", f"{duration:.3f}", "-i", str(dist_path),
        "-filter_complex", filter_complex,
        "-f", "null", "-"
    ]
    
    try:
        logger.info(f"Running VMAF comparison: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Read mean score from JSON
        if log_file.exists():
            with open(log_file, "r") as f:
                vmaf_data = json.load(f)
            # Clean up immediately
            log_file.unlink()
            return float(vmaf_data["pooled_metrics"]["vmaf"]["mean"])
            
        # Regex fallback if json log fails
        # Parsed_libvmaf_2 ... VMAF score: 94.12
        vmaf_match = re.search(r"VMAF score:\s*([\d\.]+)", res.stderr)
        if vmaf_match:
            return float(vmaf_match.group(1))
            
        raise RuntimeError("VMAF score output not found in FFmpeg output.")
    except Exception as e:
        logger.error(f"VMAF calculation failed: {e}")
        # Clean up log file if it exists
        if log_file.exists():
            log_file.unlink()
        raise e

def run_vmaf_search(
    input_path: Path,
    codec: str,
    preset: str,
    pix_fmt: str,
    filters: Optional[str],
    target_vmaf: float,
    crf_range: Tuple[int, int],
    duration: float,
    use_mpdecimate: bool,
    duplicate_threshold: float = 0.001,
    model_type: str = "1080p",
    video_width: int = 1920,
    video_height: int = 1080,
    job_id: Optional[int] = None
) -> int:
    """
    Performs Binary Search optimization to find the CRF that yields target VMAF.
    Selects 3 segments of 10s at 20%, 50%, and 80% marks.
    """
    crf_min, crf_max = crf_range
    segment_duration = 10.0
    
    # 20%, 50%, 80% offsets
    timestamps = [duration * 0.2, duration * 0.5, duration * 0.8]
    # Filter offsets if duration is too small
    timestamps = [t for t in timestamps if t + segment_duration < duration]
    if not timestamps:
        timestamps = [0.0]
        
    logger.info(f"VMAF auto-CRF search starting. Target VMAF: {target_vmaf}. Range: {crf_range}. Samples at: {timestamps}")
    
    best_crf = int((crf_min + crf_max) / 2)
    iterations = 0
    max_iterations = 4
    
    while crf_min <= crf_max and iterations < max_iterations:
        if job_id is not None:
            from app.database import get_job
            j_state = get_job(job_id)
            if j_state and j_state["status"] == "cancelled":
                logger.info(f"VMAF search for job {job_id} aborted because job was cancelled.")
                raise Exception("Job cancelled")

        current_crf = int((crf_min + crf_max) / 2)
        iterations += 1
        scores = []
        
        logger.info(f"Iteration {iterations}: Testing CRF {current_crf}")
        
        # Test CRF on each segment
        for idx, ts in enumerate(timestamps):
            if job_id is not None:
                from app.database import get_job
                j_state = get_job(job_id)
                if j_state and j_state["status"] == "cancelled":
                    logger.info(f"VMAF search for job {job_id} aborted because job was cancelled.")
                    raise Exception("Job cancelled")
                
                # Update progress
                total_steps = max_iterations * len(timestamps)
                current_step = (iterations - 1) * len(timestamps) + idx
                progress_pct = (current_step / total_steps) * 100.0
                set_running_progress(job_id, {
                    "phase": "vmaf",
                    "progress": progress_pct,
                    "fps": 0.0,
                    "speed": "N/A",
                    "eta": f"Iteration {iterations}/{max_iterations} (segment {idx + 1}/{len(timestamps)})",
                    "ffmpeg_pid": 0
                })
            temp_out = TEMP_DIR / f"test_segment_{idx}_{current_crf}.mp4"
            
            # Setup transcoding parameters for segment
            cmd_segment = [
                "ffmpeg", "-y",
                "-ss", f"{ts:.3f}", "-t", f"{segment_duration:.3f}", "-i", str(input_path),
                "-c:v", codec, "-crf", str(current_crf), "-preset", preset,
                "-pix_fmt", pix_fmt
            ]
            
            # Add decimate/video filters
            if filters:
                cmd_segment += ["-vf", filters]
                
            cmd_segment += ["-an", "-sn", str(temp_out)]
            
            try:
                # Transcode segment
                subprocess.run(cmd_segment, capture_output=True, check=True)
                
                # Calculate VMAF on segment
                score = run_vmaf_comparison(
                    ref_path=input_path,
                    dist_path=temp_out,
                    start_time=ts,
                    duration=segment_duration,
                    use_mpdecimate=use_mpdecimate,
                    duplicate_threshold=duplicate_threshold,
                    model_type=model_type,
                    video_width=video_width,
                    video_height=video_height
                )
                scores.append(score)
            except Exception as e:
                logger.error(f"VMAF test segment {idx} failed for CRF {current_crf}: {e}")
                # Treat failure as bad VMAF to keep searching
                scores.append(0.0)
            finally:
                # Clean up temporary video segment
                if temp_out.exists():
                    temp_out.unlink()
                    
        avg_vmaf = sum(scores) / len(scores) if scores else 0.0
        logger.info(f"CRF {current_crf} achieved average VMAF: {avg_vmaf:.2f}")
        
        # Check termination or adjust bounds
        if abs(avg_vmaf - target_vmaf) < 0.5:
            best_crf = current_crf
            break
            
        if avg_vmaf < target_vmaf:
            # Under target VMAF: needs more quality (lower CRF)
            crf_max = current_crf - 1
        else:
            # Over target VMAF: can afford less quality (higher CRF)
            best_crf = current_crf # Save current as viable backup
            crf_min = current_crf + 1
            
    logger.info(f"VMAF search finished. Selected CRF: {best_crf}")
    return best_crf

def transcode_video(job_id: int):
    """
    Executes full transcode logic, updates live status dictionary, and saves results.
    """
    global running_job_process
    
    transcode_start_time = time.time()
    
    # 1. Fetch Job info
    job = get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in database.")
        return
        
    input_path = Path(job["input_path"])
    output_path = Path(job["output_path"])
    
    # Prepare parent directory for output if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    config = json.loads(job["preset_config"])
    video_cfg = config.get("video", {})
    audio_cfg = config.get("audio", {})
    sub_cfg = config.get("subtitles", {})
    opt_cfg = config.get("optimization", {})
    out_cfg = config.get("output", {})
    
    codec = video_cfg.get("codec", "libx264")
    preset = str(video_cfg.get("preset", "fast"))
    pix_fmt = video_cfg.get("pixel_format", "yuv420p")
    target_vmaf = float(opt_cfg.get("target_vmaf", 0.0))
    dedup = bool(opt_cfg.get("duplicate_frame_detection", False))
    
    # Probe source metadata
    meta = probe_video(input_path)
    duration = meta["duration"]
    source_fps = meta["fps"]
    
    # Store probed metadata in DB
    update_job(job_id, source_fps=source_fps)
    
    # Adjust VMAF CRF bounds
    crf_range = opt_cfg.get("vmaf_search_range", [18, 30])
    
    # Select CRF
    crf = video_cfg.get("crf", 22)
    
    # Prepare video filters
    vf_filters = []
    if dedup:
        threshold = opt_cfg.get("duplicate_threshold", 0.001)
        vf_filters.append(f"mpdecimate=max=0:hi=64:lo=64:frac={threshold}")
        
    # Check subtitle burn-in
    sub_mode = sub_cfg.get("mode", "none")
    burn_in_track = None
    
    if sub_mode == "burn-in":
        # Find index to burn-in
        burn_in_select = sub_cfg.get("burn_in_track_select", "default")
        tracks = meta["subtitles"]
        
        if isinstance(burn_in_select, int):
            # Select by index
            burn_in_track = next((t for t in tracks if t["index"] == burn_in_select), None)
        elif burn_in_select == "forced":
            # First forced
            burn_in_track = next((t for t in tracks if t["is_forced"]), None)
            
        if not burn_in_track:
            # Fallback to first default or first overall
            burn_in_track = next((t for t in tracks if t["is_default"]), None)
            if not burn_in_track and tracks:
                burn_in_track = tracks[0]
                
        if burn_in_track:
            update_job(job_id, selected_subtitle_track=burn_in_track["index"])
            
    # Resolve Auto-CRF if requested
    if target_vmaf > 0.0:
        # Update status to vmaf
        update_job(job_id, status="vmaf")
        # Run binary search
        vf_string = ",".join(vf_filters) if vf_filters else None
        crf = run_vmaf_search(
            input_path=input_path,
            codec=codec,
            preset=preset,
            pix_fmt=pix_fmt,
            filters=vf_string,
            target_vmaf=target_vmaf,
            crf_range=tuple(crf_range),
            duration=duration,
            use_mpdecimate=dedup,
            duplicate_threshold=opt_cfg.get("duplicate_threshold", 0.001),
            model_type=opt_cfg.get("vmaf_model", "1080p"),
            video_width=meta.get("width", 1920),
            video_height=meta.get("height", 1080),
            job_id=job_id
        )
        
        # Check if cancelled during VMAF search
        j_state = get_job(job_id)
        if j_state and j_state["status"] == "cancelled":
            logger.info(f"VMAF search for job {job_id} completed but job was already cancelled.")
            return

        # Update status back to running with selected CRF
        update_job(job_id, status="running", selected_crf=crf)
    else:
        update_job(job_id, selected_crf=crf)
        
    # Construct complete transcode FFmpeg command
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    
    # Build Video args
    cmd += ["-c:v", codec, "-crf", str(crf), "-preset", preset, "-pix_fmt", pix_fmt]
    
    # Check custom frame rates
    fps = video_cfg.get("fps", "same as source")
    fps_mode = video_cfg.get("fps_mode", "constant")
    
    if fps != "same as source":
        cmd += ["-r", str(fps)]
        
    if fps_mode == "constant":
        cmd += ["-fps_mode", "cfr"]
    else:
        cmd += ["-fps_mode", "vfr"]
        
    # Subtitle burn-in vs filters complex assembly
    if burn_in_track:
        t_codec = burn_in_track["codec"]
        t_track_id = burn_in_track["track_id"]
        
        # If it's image-based subtitle (pgs, dvdsub)
        if "pgs" in t_codec or "dvd" in t_codec or "vob" in t_codec:
            # Complex filter overlay
            threshold = opt_cfg.get("duplicate_threshold", 0.001)
            decimate_node = f"[0:v]mpdecimate=max=0:hi=64:lo=64:frac={threshold}[dec];" if dedup else ""
            v_input = "[dec]" if dedup else "[0:v]"
            filter_complex = f"{decimate_node}{v_input}[0:s:{t_track_id}]overlay[v]"
            cmd += ["-filter_complex", filter_complex, "-map", "[v]"]
        else:
            # Text based: apply subtitle vf filter
            escaped_input = escape_filter_path(input_path)
            vf_filters.append(f"subtitles='{escaped_input}':si={t_track_id}")
            cmd += ["-vf", ",".join(vf_filters), "-map", "0:v:0"]
    else:
        if vf_filters:
            cmd += ["-vf", ",".join(vf_filters)]
        cmd += ["-map", "0:v:0"]

    # Build Audio args (Multiple mapping logic)
    # Probe source audio streams
    cmd_audio_probe = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,codec_name", "-of", "json", str(input_path)
    ]
    try:
        res_audio = subprocess.run(cmd_audio_probe, capture_output=True, text=True, check=True)
        audio_streams = json.loads(res_audio.stdout).get("streams", [])
    except Exception:
        audio_streams = []

    # Mapping rules
    pass_codecs = audio_cfg.get("passthrough_codecs", [])
    fallback_codec = audio_cfg.get("fallback_codec", "aac")
    fallback_bitrate = int(audio_cfg.get("fallback_bitrate", 192000))
    fallback_bitrate_kb = f"{int(fallback_bitrate / 1000)}k"

    for idx, stream in enumerate(audio_streams):
        s_idx = stream["index"]
        s_codec = stream["codec_name"]
        
        cmd += ["-map", f"0:a:{idx}"]
        
        # Check passthrough
        if s_codec in pass_codecs:
            cmd += [f"-c:a:{idx}", "copy"]
        else:
            cmd += [f"-c:a:{idx}", fallback_codec, f"-b:a:{idx}", fallback_bitrate_kb]

    # Build Subtitle Soft Passthrough
    if sub_mode == "passthrough":
        container = out_cfg.get("container", "mkv")
        cmd += ["-map", "0:s?"]
        if container == "mp4":
            cmd += ["-c:s", "mov_text"]
        else:
            cmd += ["-c:s", "copy"]
    elif sub_mode == "none":
        # Discard subtitle streams explicitly
        cmd += ["-sn"]

    cmd += ["-progress", "pipe:1", str(output_path)]
    
    # Save the generated command in jobs DB
    cmd_str = " ".join(cmd)
    update_job(job_id, ffmpeg=cmd_str)
    
    logger.info(f"Starting transcode process: {cmd_str}")
    
    # Set progress initialized
    set_running_progress(job_id, {
        "progress": 0.0,
        "fps": 0.0,
        "speed": "0x",
        "eta": "Calculating...",
        "ffmpeg_pid": 0
    })
    
    # Run FFmpeg process
    try:
        running_job_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        # Store PID
        set_running_progress(job_id, {
            "progress": 0.0,
            "fps": 0.0,
            "speed": "0x",
            "eta": "Calculating...",
            "ffmpeg_pid": running_job_process.pid
        })
        
        # Parse stdout/stderr progress updates
        out_reader = running_job_process.stdout
        current_frame = 0
        current_time_ms = 0
        current_fps = 0.0
        current_speed = "0.0x"
        
        while True:
            line = out_reader.readline()
            if not line:
                break
                
            line = line.strip()
            
            # Match progress values
            if line.startswith("frame="):
                try:
                    current_frame = int(line.split("=")[1].strip())
                except ValueError:
                    pass
            elif line.startswith("fps="):
                try:
                    current_fps = float(line.split("=")[1].strip())
                except ValueError:
                    pass
            elif line.startswith("speed="):
                current_speed = line.split("=")[1].strip()
            elif line.startswith("out_time_ms="):
                try:
                    current_time_ms = int(line.split("=")[1].strip())
                    
                    # Convert ms to seconds
                    elapsed_seconds = current_time_ms / 1000000.0
                    progress_pct = (elapsed_seconds / duration * 100) if duration > 0 else 0.0
                    progress_pct = min(100.0, max(0.0, progress_pct))
                    
                    # Calculate ETA
                    eta_str = "Calculating..."
                    if current_fps > 0 and duration > 0:
                        total_expected = meta["nb_frames"]
                        if total_expected <= 0:
                            total_expected = duration * source_fps
                        remaining_frames = max(0, total_expected - current_frame)
                        rem_seconds = remaining_frames / current_fps
                        
                        m, s = divmod(int(rem_seconds), 60)
                        h, m = divmod(m, 60)
                        eta_str = f"{h:02d}:{m:02d}:{s:02d}"
                        
                    set_running_progress(job_id, {
                        "progress": progress_pct,
                        "fps": current_fps,
                        "speed": current_speed,
                        "eta": eta_str,
                        "ffmpeg_pid": running_job_process.pid
                    })
                except ValueError:
                    pass
                    
        # Wait for finish
        ret_code = running_job_process.wait()
        
        if ret_code == 0:
            # Success!
            logger.info(f"FFmpeg transcode completed successfully for job {job_id}.")
            
            # Post-Transcode Metrics & Verification
            out_meta = probe_video(output_path)
            result_fps = out_meta["fps"]
            
            # Output size metrics
            in_size = input_path.stat().st_size
            out_size = output_path.stat().st_size
            relative_size = int((out_size / in_size) * 100) if in_size > 0 else 100
            
            # Final VMAF Calculation
            measured_vmaf = None
            calc_final_vmaf = bool(opt_cfg.get("calculate_final_vmaf", True))
            final_vmaf_mode = str(opt_cfg.get("final_vmaf_mode", "sample"))
            
            if duration > 0 and calc_final_vmaf:
                try:
                    logger.info(f"Computing final verification VMAF score (mode: {final_vmaf_mode})...")
                    if final_vmaf_mode == "full":
                        vmaf_sample_start = 0.0
                        vmaf_sample_len = duration
                    else:
                        vmaf_sample_start = max(0.0, (duration / 2.0) - 30.0)
                        vmaf_sample_len = min(60.0, duration)
                        
                    measured_vmaf = run_vmaf_comparison(
                        ref_path=input_path,
                        dist_path=output_path,
                        start_time=vmaf_sample_start,
                        duration=vmaf_sample_len,
                        use_mpdecimate=dedup,
                        duplicate_threshold=opt_cfg.get("duplicate_threshold", 0.001),
                        model_type=opt_cfg.get("vmaf_model", "1080p"),
                        video_width=meta.get("width", 1920),
                        video_height=meta.get("height", 1080),
                        dist_start_time=vmaf_sample_start
                    )
                    logger.info(f"Final measured VMAF: {measured_vmaf}")
                except Exception as ex:
                    logger.warning(f"Failed to calculate final VMAF check: {ex}")
                    
            # Compute actual unduplicated FPS
            unduplicated_fps = source_fps
            if dedup:
                # If decimated, get actual output frame count
                unduplicated_fps = out_meta["nb_frames"] / duration if duration > 0 else source_fps
                
            # Update DB details first
            update_job(
                job_id,
                duration=int(duration),
                relative_size=relative_size,
                result_fps=result_fps,
                unduplicated_fps=unduplicated_fps,
                measured_vmaf=measured_vmaf
            )
            
            transcode_time_taken = time.time() - transcode_start_time
            if bool(out_cfg.get("save_info_file", False)):
                final_job = get_job(job_id)
                if final_job:
                    final_job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    write_info_txt(final_job, transcode_time_taken)
                    
            # Finally, mark completed so the UI transitions
            update_job(
                job_id,
                status="completed",
                finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            # Failed
            logger.error(f"FFmpeg failed with exit code: {ret_code}")
            
            # Check if cancelled vs crashed
            job_state = get_job(job_id)
            if job_state and job_state["status"] == "cancelled":
                logger.info(f"Job {job_id} cancelled.")
            else:
                update_job(
                    job_id,
                    status="failed",
                    failed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    error=f"FFmpeg exited with error code {ret_code}"
                )
    except Exception as e:
        logger.error(f"Error executing transcode: {e}")
        job_state = get_job(job_id)
        if job_state and job_state["status"] == "cancelled":
            logger.info(f"Job {job_id} was cancelled.")
        else:
            update_job(
                job_id,
                status="failed",
                failed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                error=str(e)
            )
    finally:
        clear_running_progress(job_id)
        running_job_process = None

def cancel_running_job(job_id: int) -> bool:
    """Cancels the currently running transcode process cleanly."""
    global running_job_process, running_job_id
    
    with worker_lock:
        job = get_job(job_id)
        if not job:
            return False
            
        if job["status"] in ("running", "vmaf"):
            # Update database first to mark cancelled
            update_job(
                job_id,
                status="cancelled",
                cancelled_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            # Kill FFmpeg process
            if running_job_process:
                logger.info(f"Terminating FFmpeg PID {running_job_process.pid} for job {job_id}")
                try:
                    running_job_process.terminate()
                    # Wait up to 5s for clean shutdown
                    for _ in range(50):
                        if running_job_process.poll() is not None:
                            break
                        time.sleep(0.1)
                    if running_job_process.poll() is None:
                        running_job_process.kill()
                except Exception as e:
                    logger.error(f"Error terminating process: {e}")
            
            # Delete incomplete output file
            out_file = Path(job["output_path"])
            if out_file.exists():
                try:
                    out_file.unlink()
                    logger.info(f"Deleted incomplete transcode output file: {out_file}")
                except OSError as e:
                    logger.error(f"Failed to delete incomplete file: {e}")
            return True
            
        elif job["status"] == "pending":
            # Cancel a pending job
            from app.database import remove_from_transcode_next
            # Remove from transcode next queue
            remove_from_transcode_next(job_id)
            # Update status
            update_job(
                job_id,
                status="cancelled",
                cancelled_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            return True
            
    return False

def worker_loop():
    """Background processing loop executing job entries sequentially."""
    global running_job_id, queue_paused
    logger.info("Background queue worker thread started.")
    
    while True:
        try:
            if queue_paused:
                time.sleep(2.0)
                continue
                
            # Pull next pending job
            from app.database import start_next_job
            job = start_next_job()
            
            if job:
                running_job_id = job["id"]
                logger.info(f"Processing job ID: {running_job_id}")
                transcode_video(running_job_id)
                running_job_id = None
            else:
                time.sleep(2.0)
        except Exception as e:
            logger.error(f"Error in queue worker loop iteration: {e}")
            time.sleep(5.0)

def start_worker():
    """Initialize and start the background transcode worker thread."""
    global worker_thread
    with worker_lock:
        if worker_thread is None or not worker_thread.is_alive():
            worker_thread = threading.Thread(target=worker_loop, name="TranscodeWorker", daemon=True)
            worker_thread.start()
            logger.info("Spawned new background transcode thread.")

def pause_queue():
    """Pauls processing loop."""
    global queue_paused
    queue_paused = True
    logger.info("Queue processing PAUSED.")

def resume_queue():
    """Resume processing loop."""
    global queue_paused
    queue_paused = False
    logger.info("Queue processing RESUMED.")
    start_worker()

# Startup Recovery & Crash Handling Design
def recover_orphaned_jobs():
    """
    Looks for jobs left in 'running' state on boot and triggers
    recovery actions according to system configuration settings.
    """
    logger.info("Running startup orphaned jobs recovery check...")
    
    action = get_setting("on_startup_orphaned_job_action", "mark_failed_pause")
    
    # Query database for jobs currently 'running'
    with db_conn() as conn:
        cur = conn.execute("SELECT id, output_path FROM jobs WHERE status IN ('running', 'vmaf');")
        orphaned = [dict(row) for row in cur.fetchall()]
        
    if not orphaned:
        logger.info("No orphaned jobs found on boot.")
        return
        
    logger.warning(f"Discovered {len(orphaned)} orphaned 'running' jobs. Action: {action}")
    
    for job in orphaned:
        job_id = job["id"]
        out_path = Path(job["output_path"])
        
        if action in ("mark_failed_pause", "mark_failed_resume"):
            # Mark failed
            update_job(
                job_id,
                status="failed",
                failed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                error="Job interrupted due to unexpected application shutdown or container restart"
            )
            logger.info(f"Marked orphaned job {job_id} as failed.")
            if action == "mark_failed_pause":
                pause_queue()
                
        elif action == "auto_restart":
            # Delete incomplete file
            if out_path.exists():
                try:
                    out_path.unlink()
                    logger.info(f"Cleaned up orphaned output file: {out_path}")
                except Exception as ex:
                    logger.error(f"Failed to delete orphaned file: {ex}")
            # Reset to pending
            update_job(
                job_id,
                status="pending",
                started_at=None,
                error=None
            )
            logger.info(f"Re-queued orphaned job {job_id} to pending.")
            resume_queue()


def format_size(bytes_size: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}" if bytes_size > 0 else f"0 {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS or SS.Ss."""
    if seconds >= 60:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}h {m:02d}m {s:02d}s"
        return f"{m:02d}m {s:02d}s"
    return f"{seconds:.2f}s"

def write_info_txt(job: dict, transcode_time_taken: float):
    """Write transcode summary info.txt next to output video."""
    try:
        output_path = Path(job["output_path"])
        input_path = Path(job["input_path"])
        info_path = output_path.parent / f"{output_path.stem}_info.txt"
        
        in_size = input_path.stat().st_size if input_path.exists() else 0
        out_size = output_path.stat().st_size if output_path.exists() else 0
        
        duration_sec = job.get("duration", 0) or 0
        duration_str = format_duration(duration_sec)
        transcode_time_str = format_duration(transcode_time_taken)
        
        # Calculate speed ratio (video duration / transcode time)
        speed_ratio = (duration_sec / transcode_time_taken) if transcode_time_taken > 0 else 0.0
        
        preset_config = {}
        if job.get("preset_config"):
            try:
                preset_config = json.loads(job["preset_config"])
            except Exception:
                pass
                
        vid_cfg = preset_config.get("video", {})
        aud_cfg = preset_config.get("audio", {})
        sub_cfg = preset_config.get("subtitles", {})
        opt_cfg = preset_config.get("optimization", {})
        
        lines = [
            "============================================================",
            "                     ebrake Transcode Info                  ",
            "============================================================",
            f"Job ID:         {job.get('id')}",
            f"Status:         Completed",
            f"File Name:      {output_path.name}",
            f"Input Path:     {input_path}",
            f"Output Path:    {output_path}",
            f"Started At:     {job.get('started_at')}",
            f"Completed At:   {job.get('finished_at')}",
            "",
            "-------------------- Transcode Statistics -------------------",
            f"Video Duration:   {duration_str}",
            f"Transcoding Time: {transcode_time_str}",
            f"Average Speed:    {speed_ratio:.2f}x",
            f"Original Size:    {format_size(in_size)} ({in_size} bytes)",
            f"Output Size:      {format_size(out_size)} ({out_size} bytes)",
            f"Relative Size:    {job.get('relative_size', 100)}% of original",
            "",
            "-------------------- Video Metrics --------------------------",
            f"Codec:            {vid_cfg.get('codec', 'N/A')}",
            f"Preset Option:    {vid_cfg.get('preset', 'N/A')}",
            f"Constant Rate Factor (CRF): {job.get('selected_crf', 'N/A')} (Optimized by VMAF: {'Yes' if float(opt_cfg.get('target_vmaf', 0)) > 0 else 'No'})",
            f"Source FPS:       {job.get('source_fps', 'N/A')}",
            f"Output FPS:       {job.get('result_fps', 'N/A')}",
            f"Unduplicated FPS: {job.get('unduplicated_fps', 'N/A')} (FPS Deduplication: {'Enabled' if opt_cfg.get('duplicate_frame_detection') else 'Disabled'})",
            f"Final Measured VMAF: {job.get('measured_vmaf', 'N/A')}",
            "",
            "-------------------- Audio Settings -------------------------",
            f"Passthrough Codecs: {', '.join(aud_cfg.get('passthrough_codecs', [])) or 'None'}",
            f"Fallback Codec:     {aud_cfg.get('fallback_codec', 'N/A')}",
            f"Fallback Bitrate:   {aud_cfg.get('fallback_bitrate', 'N/A')}",
            "",
            "-------------------- Subtitle Settings ----------------------",
            f"Subtitle Mode:      {job.get('subtitle_mode', 'none')}",
            f"Selected Track:     {job.get('selected_subtitle_track') if job.get('selected_subtitle_track') is not None else 'None'}",
            "",
            "-------------------- FFmpeg Execution Command ---------------",
            f"{job.get('ffmpeg', 'N/A')}",
            "============================================================",
        ]
        
        with open(info_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
            
        logger.info(f"Saved transcode info.txt successfully at {info_path}")
    except Exception as e:
        logger.error(f"Failed to write info.txt: {e}")
