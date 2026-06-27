import os
import logging
import shutil
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import init_directories, PRESETS_DIR, MEDIA_DIR
from app.database import (
    init_db, get_jobs, get_job, create_job, update_job, delete_job,
    get_setting, set_setting, get_media_files, search_media_files,
    add_to_transcode_next, insert_into_transcode_next, reorder_transcode_next,
    remove_from_transcode_next
)
from app.presets import (
    init_presets, get_all_presets, get_preset, save_preset,
    delete_preset, create_category, delete_category, list_categories, list_presets
)
from app.scanner import run_library_sync, start_periodic_scanner, is_library_syncing
from app.engine import (
    start_worker, recover_orphaned_jobs, cancel_running_job,
    resume_queue, pause_queue, is_queue_paused, get_running_progress,
    run_dedup_dryrun, run_vmaf_comparison, run_vmaf_search, probe_video,
    TEMP_DIR
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize application directories
    init_directories()
    # Initialize SQLite database schema
    init_db()
    # Populate preset templates if empty
    init_presets()
    # Recover orphaned transcoding processes
    recover_orphaned_jobs()
    # Start background transcoding thread
    start_worker()
    # Launch background periodic 30-min media scanner
    scanner_task = asyncio.create_task(start_periodic_scanner())
    yield
    # Cleanup background scanner on shutdown
    scanner_task.cancel()

import asyncio

app = FastAPI(title="ebrake Transcoder", lifespan=lifespan)

# Setup Templates and Static assets mapping
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Context processor for templates to supply global states
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    # Retrieve current global privacy mode settings
    request.state.privacy_mode = get_setting("privacy_mode_enabled", False)
    request.state.queue_paused = is_queue_paused()
    response = await call_next(request)
    return response

def render_page(request: Request, template_name: str, context: Dict[str, Any] = None) -> HTMLResponse:
    """Helper to render hybrid templates: full base shell vs standalone fragment."""
    if context is None:
        context = {}
        
    # Inject request details and state flags
    context["request"] = request
    context["privacy_mode_enabled"] = get_setting("privacy_mode_enabled", False)
    context["queue_paused"] = is_queue_paused()
    
    from app.database import get_jobs
    context["any_running"] = any(j["status"] == "running" for j in get_jobs())
    
    is_htmx = request.headers.get("HX-Request") == "true"
    
    if is_htmx:
        # Return page fragment directly
        return templates.TemplateResponse(request, template_name, context)
    else:
        # Return base layout shell wrapping target page template
        context["page_template"] = template_name
        return templates.TemplateResponse(request, "base.html", context)

# PAGE ROUTES

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/create-job")


@app.get("/create-job", response_class=HTMLResponse)
async def create_job_page(request: Request):
    presets_tree = get_all_presets()
    categories = list_categories()
    
    # Load first category presets as default listing
    default_category = categories[0] if categories else ""
    default_presets = list_presets(default_category) if default_category else []
    
    # Load parameters for the first preset if exists
    default_preset_data = None
    if default_category and default_presets:
        default_preset_data = get_preset(default_category, default_presets[0])
        
    context = {
        "active_tab": "create-job",
        "presets_tree": presets_tree,
        "categories": categories,
        "current_category": default_category,
        "presets": default_presets,
        "preset": default_preset_data,
        "media_root": str(MEDIA_DIR)
    }
    return render_page(request, "create_job.html", context)

@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    # Fetch queue segments
    jobs = get_jobs()
    pending = [j for j in jobs if j["status"] == "pending"]
    running = [j for j in jobs if j["status"] == "running"]
    completed = [j for j in jobs if j["status"] == "completed"]
    failed = [j for j in jobs if j["status"] == "failed"]
    cancelled = [j for j in jobs if j["status"] == "cancelled"]
    
    # Split pending into Transcode Next vs Priority queue
    transcode_next = [j for j in pending if j["transcode_next_position"] is not None]
    normal_queue = [j for j in pending if j["transcode_next_position"] is None]
    
    context = {
        "active_tab": "jobs",
        "transcode_next": transcode_next,
        "normal_queue": normal_queue,
        "running": running,
        "history": completed + failed + cancelled
    }
    return render_page(request, "jobs.html", context)

@app.get("/presets", response_class=HTMLResponse)
async def presets_page(request: Request):
    presets_tree = get_all_presets()
    categories = list_categories()
    
    context = {
        "active_tab": "presets",
        "presets_tree": presets_tree,
        "categories": categories
    }
    return render_page(request, "presets.html", context)

@app.get("/tools", response_class=HTMLResponse)
async def tools_page(request: Request):
    categories = list_categories()
    default_category = categories[0] if categories else ""
    default_presets = list_presets(default_category) if default_category else []
    
    default_preset_data = None
    if default_category and default_presets:
        default_preset_data = get_preset(default_category, default_presets[0])
        
    context = {
        "active_tab": "tools",
        "categories": categories,
        "presets": default_presets,
        "preset": default_preset_data,
        "media_root": str(MEDIA_DIR)
    }
    return render_page(request, "tools.html", context)

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    context = {
        "active_tab": "settings",
        "on_startup_orphaned_job_action": get_setting("on_startup_orphaned_job_action", "mark_failed_pause"),
        "privacy_mode_enabled": get_setting("privacy_mode_enabled", False),
        "appdata_path": str(Path(os.getenv("EBRAKE_APPDATA_DIR", "./appdata")).resolve()),
        "media_path": str(MEDIA_DIR)
    }
    return render_page(request, "settings.html", context)

# API ENDPOINTS - MEDIA BROWSER & SCANNER

@app.get("/api/media/search", response_class=HTMLResponse)
async def api_media_search(request: Request, q: str = "", current_dir: str = ""):
    """Returns matching cached filenames (or directory structure if empty)."""
    if not q:
        # Fallback to listing directories
        target_dir = current_dir if current_dir else str(MEDIA_DIR)
        target_path = Path(target_dir).resolve()
        
        # Security boundaries check
        if not str(target_path).startswith(str(MEDIA_DIR.resolve())):
            target_path = MEDIA_DIR.resolve()
            
        files_list = []
        
        # Display folder going upwards if not at media root
        if target_path != MEDIA_DIR.resolve():
            files_list.append({
                "path": str(target_path.parent),
                "name": ".. [Up One Level]",
                "parent_path": str(target_path.parent.parent),
                "is_dir": 1,
                "size": 0,
                "mtime": 0.0
            })
            
        try:
            with os.scandir(target_path) as it:
                for entry in it:
                    stat = entry.stat(follow_symlinks=False)
                    is_dir = entry.is_dir(follow_symlinks=False)
                    files_list.append({
                        "path": str(Path(entry.path).resolve()),
                        "name": entry.name,
                        "parent_path": str(target_path),
                        "is_dir": 1 if is_dir else 0,
                        "size": stat.st_size if not is_dir else 0,
                        "mtime": stat.st_mtime
                    })
        except OSError:
            pass
            
        # Order folders first
        files_list.sort(key=lambda x: (x["name"] == ".. [Up One Level]", not x["is_dir"], x["name"].lower()))
    else:
        # Search via cache DB
        files_list = search_media_files(q)
        
    return templates.TemplateResponse(request, "components/file_browser_list.html", {
        "files": files_list,
        "current_dir": current_dir if current_dir else str(MEDIA_DIR),
        "query": q
    })

@app.post("/api/media/sync", response_class=HTMLResponse)
async def api_media_sync(request: Request, background_tasks: BackgroundTasks):
    """Triggers file scanner in background thread."""
    if not is_library_syncing():
        background_tasks.add_task(run_library_sync)
        
    return """
    <button class="btn btn-icon" 
            hx-get="/api/media/sync/status" 
            hx-trigger="every 1s" 
            hx-swap="outerHTML" 
            disabled>
        <i class="fa-solid fa-circle-notch fa-spin"></i>
        <span>Updating</span>
    </button>
    """

@app.get("/api/media/sync/status", response_class=HTMLResponse)
async def api_media_sync_status(request: Request):
    """Check sync progress and return active/disabled button accordingly."""
    if is_library_syncing():
        return """
        <button class="btn btn-icon" 
                hx-get="/api/media/sync/status" 
                hx-trigger="every 1s" 
                hx-swap="outerHTML" 
                disabled>
            <i class="fa-solid fa-circle-notch fa-spin"></i>
            <span>Updating</span>
        </button>
        """
    else:
        return """
        <button class="btn btn-icon" 
                style="background-color: var(--color-success) !important; color: #ffffff !important; border-color: var(--color-success) !important;"
                hx-get="/api/media/sync/reset" 
                hx-trigger="load delay:2s" 
                hx-swap="outerHTML"
                title="Sync successful">
            <i class="fa-solid fa-check"></i>
            <span>Sync successful</span>
        </button>
        """

@app.get("/api/media/sync/reset", response_class=HTMLResponse)
async def api_media_sync_reset(request: Request):
    """Reset the media sync button back to idle state."""
    return """
    <button class="btn btn-icon" 
            hx-post="/api/media/sync" 
            hx-swap="outerHTML" 
            title="Rescan media directory">
        <i class="fa-solid fa-rotate"></i>
        <span>Update search db</span>
    </button>
    """

# API ENDPOINTS - PRESETS MANAGEMENT

@app.get("/api/presets/select", response_class=HTMLResponse)
async def api_preset_select_preset(request: Request, category: str, preset: str):
    """Loads a preset details configurations to pre-populate configuration overrides panel."""
    preset_data = get_preset(category, preset)
    if not preset_data:
        raise HTTPException(status_code=404, detail="Preset not found")
        
    return templates.TemplateResponse(request, "components/preset_overrides.html", {
        "preset": preset_data
    })

@app.get("/api/presets/presets-list", response_class=HTMLResponse)
async def api_presets_list_presets(request: Request, category: str):
    """Fetches list of presets inside a category."""
    presets = list_presets(category)
    return "".join([f"<option value='{p}'>{p}</option>" for p in presets])

@app.get("/api/presets/config-fields", response_class=HTMLResponse)
async def api_preset_config_fields(request: Request, category: str, name: Optional[str] = None):
    """Returns a full preset config form for editing inside Presets tab."""
    preset_data = get_preset(category, name) if name else None
    return templates.TemplateResponse(request, "components/preset_config_form.html", {
        "category": category,
        "preset_name": name,
        "preset": preset_data
    })

@app.post("/api/presets/save", response_class=HTMLResponse)
async def api_preset_save(
    request: Request,
    category: str = Form(...),
    preset_name: str = Form(...),
    original_preset_name: Optional[str] = Form(None),
    codec: str = Form(...),
    preset_val: str = Form(...),
    crf: int = Form(...),
    visual_tune: int = Form(0),
    fps: str = Form("same as source"),
    fps_mode: str = Form("constant"),
    pixel_format: str = Form("yuv420p"),
    target_vmaf: float = Form(0.0),
    vmaf_min: int = Form(18),
    vmaf_max: int = Form(30),
    vmaf_model: str = Form("1080p"),
    dedup: bool = Form(False),
    passthrough_codecs: List[str] = Form([]),
    fallback_codec: str = Form("aac"),
    fallback_bitrate: int = Form(192000),
    sub_mode: str = Form("none"),
    burn_in_track_select: str = Form("default"),
    output_suffix: str = Form(""),
    container: str = Form("mkv"),
    save_info_file: bool = Form(False)
):
    """Save/update preset ebrake TOML file."""
    # Collision check
    rename_occurred = False
    if original_preset_name and original_preset_name != preset_name:
        existing = get_preset(category, preset_name)
        if existing:
            response_html = f"<div class='alert alert-danger'>A preset named '{preset_name}' already exists in category '{category}'.</div>"
            return HTMLResponse(content=response_html)
        rename_occurred = True

    # Build preset structure
    preset_data = {
        "video": {
            "codec": codec,
            "preset": preset_val,
            "crf": crf,
            "visual_tune": visual_tune,
            "fps": fps,
            "fps_mode": fps_mode,
            "pixel_format": pixel_format
        },
        "optimization": {
            "target_vmaf": target_vmaf,
            "vmaf_search_range": [vmaf_min, vmaf_max],
            "duplicate_frame_detection": dedup,
            "duplicate_threshold": 0.001,
            "vmaf_model": vmaf_model
        },
        "audio": {
            "passthrough_codecs": passthrough_codecs,
            "fallback_codec": fallback_codec,
            "fallback_bitrate": fallback_bitrate
        },
        "subtitles": {
            "mode": sub_mode,
            "languages": ["all"],
            "burn_in_track_select": burn_in_track_select
        },
        "output": {
            "output_suffix": output_suffix,
            "container": container,
            "save_info_file": save_info_file
        }
    }
    
    success = save_preset(category, preset_name, preset_data)
    
    # If rename was successful, delete the old preset BEFORE listing presets for tree reload
    if success and rename_occurred:
        delete_preset(category, original_preset_name)
    
    # Return HTML message + reload categories tree
    response_html = ""
    # Trigger categories out-of-band updates
    tree_html = templates.TemplateResponse(request, "components/presets_tree.html", {
        "presets_tree": get_all_presets(),
        "categories": list_categories()
    }).body.decode()
    response_html += f"<div id='presets-tree-root' hx-swap-oob='true'>{tree_html}</div>"
    
    if success and rename_occurred:
        form_html = templates.TemplateResponse(request, "components/preset_config_form.html", {
            "category": category,
            "preset_name": preset_name,
            "preset": preset_data,
            "just_renamed": True
        }).body.decode()
        response_html += f"<div id='preset-config-container' class='panel card glass' hx-swap-oob='true'>{form_html}</div>"
        
    return HTMLResponse(content=response_html, headers={"HX-Trigger": "presetChanged"})

@app.post("/api/presets/category/create", response_class=HTMLResponse)
async def api_create_category(request: Request, name: str = Form(...)):
    """Create new category folder."""
    create_category(name)
    return templates.TemplateResponse(request, "components/presets_tree.html", {
        "presets_tree": get_all_presets(),
        "categories": list_categories()
    })

@app.delete("/api/presets/category/{name}", response_class=HTMLResponse)
async def api_delete_category(request: Request, name: str):
    """Delete a preset category folder recursively."""
    delete_category(name)
    return templates.TemplateResponse(request, "components/presets_tree.html", {
        "presets_tree": get_all_presets(),
        "categories": list_categories()
    })

@app.delete("/api/presets/{category}/{name}", response_class=HTMLResponse)
async def api_delete_preset(request: Request, category: str, name: str):
    """Delete preset .ebrake file."""
    delete_preset(category, name)
    return templates.TemplateResponse(request, "components/presets_tree.html", {
        "presets_tree": get_all_presets(),
        "categories": list_categories()
    })

@app.post("/api/presets/move", response_class=HTMLResponse)
async def api_preset_move(
    request: Request,
    preset_name: str = Form(...),
    from_category: str = Form(...),
    to_category: str = Form(...)
):
    """Move preset file from one category directory to another."""
    from_path = PRESETS_DIR / from_category / f"{preset_name}.ebrake"
    to_path = PRESETS_DIR / to_category / f"{preset_name}.ebrake"
    
    headers = {}
    if not from_path.exists():
        headers["HX-Trigger"] = json.dumps({"presetMoveCollision": f"Preset '{preset_name}' not found."})
    elif to_path.exists():
        headers["HX-Trigger"] = json.dumps({"presetMoveCollision": f"A preset named '{preset_name}' already exists in category '{to_category}'."})
    else:
        try:
            shutil.move(str(from_path), str(to_path))
        except Exception as e:
            logger.error(f"Failed to move preset: {e}")
            headers["HX-Trigger"] = json.dumps({"presetMoveCollision": f"System error moving preset: {e}"})
            
    # Always return tree HTML so the list remains valid and updates
    tree_html = templates.TemplateResponse(request, "components/presets_tree.html", {
        "presets_tree": get_all_presets(),
        "categories": list_categories()
    })
    
    # Apply headers if any
    for k, v in headers.items():
        tree_html.headers[k] = v
        
    return tree_html

# API ENDPOINTS - JOBS CRUD & QUEUE REORDERING

@app.post("/api/jobs", response_class=HTMLResponse)
async def api_create_job(
    request: Request,
    input_path: str = Form(...),
    category: str = Form(...),
    preset: str = Form(...),
    priority: int = Form(0),
    codec: str = Form(...),
    preset_val: str = Form(...), # Preset name (e.g. fast)
    crf: int = Form(...),
    visual_tune: int = Form(0),
    fps: str = Form("same as source"),
    fps_mode: str = Form("constant"),
    pixel_format: str = Form("yuv420p"),
    target_vmaf: float = Form(0.0),
    vmaf_min: int = Form(18),
    vmaf_max: int = Form(30),
    vmaf_model: str = Form("1080p"),
    dedup: bool = Form(False),
    passthrough_codecs: List[str] = Form([]),
    fallback_codec: str = Form("aac"),
    fallback_bitrate: int = Form(192000),
    sub_mode: str = Form("none"),
    burn_in_track_select: str = Form("default"),
    output_suffix: str = Form(""),
    container: str = Form("mkv"),
    save_info_file: bool = Form(False)
):
    """Validate configurations, compute outputs paths (handling collisions), and insert job."""
    in_file = Path(input_path)
    if not in_file.exists():
        raise HTTPException(status_code=400, detail="Input file does not exist.")
        
    # Check is_customized comparison with original preset values
    original = get_preset(category, preset)
    is_customized = 0
    if original:
        orig_vid = original.get("video", {})
        orig_opt = original.get("optimization", {})
        if (orig_vid.get("codec") != codec or
            str(orig_vid.get("preset")) != preset_val or
            orig_vid.get("crf") != crf or
            orig_vid.get("fps") != fps or
            orig_vid.get("fps_mode") != fps_mode or
            orig_vid.get("pixel_format") != pixel_format or
            float(orig_opt.get("target_vmaf", 0.0)) != target_vmaf or
            orig_opt.get("vmaf_model", "1080p") != vmaf_model or
            bool(orig_opt.get("duplicate_frame_detection", False)) != dedup or
            original.get("audio", {}).get("passthrough_codecs", []) != passthrough_codecs or
            original.get("subtitles", {}).get("mode", "none") != sub_mode or
            bool(original.get("output", {}).get("save_info_file", False)) != save_info_file):
            is_customized = 1

    # Compile the final configuration parameters used
    resolved_config = {
        "video": {
            "codec": codec,
            "preset": preset_val,
            "crf": crf,
            "visual_tune": visual_tune,
            "fps": fps,
            "fps_mode": fps_mode,
            "pixel_format": pixel_format
        },
        "optimization": {
            "target_vmaf": target_vmaf,
            "vmaf_search_range": [vmaf_min, vmaf_max],
            "duplicate_frame_detection": dedup,
            "duplicate_threshold": 0.001,
            "vmaf_model": vmaf_model
        },
        "audio": {
            "passthrough_codecs": passthrough_codecs,
            "fallback_codec": fallback_codec,
            "fallback_bitrate": fallback_bitrate
        },
        "subtitles": {
            "mode": sub_mode,
            "languages": ["all"],
            "burn_in_track_select": burn_in_track_select
        },
        "output": {
            "output_suffix": output_suffix,
            "container": container,
            "save_info_file": save_info_file
        }
    }
    
    # Calculate output file path with collision avoidance
    out_dir = in_file.parent
    base_stem = in_file.stem
    cand_name = f"{base_stem}{output_suffix}.{container}"
    out_file = out_dir / cand_name
    
    # Avoid collisions
    counter = 1
    while out_file.exists():
        cand_name = f"{base_stem}{output_suffix}_{counter}.{container}"
        out_file = out_dir / cand_name
        counter += 1
        
    # Map model DB fields
    job_data = {
        "status": "pending",
        "input_path": str(in_file.resolve()),
        "output_path": str(out_file.resolve()),
        "priority": priority,
        "category": category,
        "preset": preset,
        "is_customized": is_customized,
        "preset_config": json.dumps(resolved_config),
        "subtitle_mode": sub_mode,
        "target_vmaf": target_vmaf if target_vmaf > 0 else None,
        "selected_crf": crf if target_vmaf <= 0 else None
    }
    
    create_job(job_data)
    
    # Start transcoding worker
    start_worker()
    
    # Redirect user to the jobs queue page via HTMX header
    return HTMLResponse(content="", headers={"HX-Redirect": "/jobs"})

# JSON Models for sorting reordering payloads
class ReorderPayload(BaseModel):
    job_id: int
    from_pos: int
    to_pos: int

class TranscodeNextPayload(BaseModel):
    job_id: int
    target_pos: int

@app.post("/api/jobs/reorder", response_class=HTMLResponse)
async def api_reorder_jobs(request: Request, payload: ReorderPayload):
    """Handles drag'n'drop sorting indices reordering within Transcode Next queue."""
    reorder_transcode_next(payload.job_id, payload.from_pos, payload.to_pos)
    return await render_queues_fragment(request)

@app.post("/api/jobs/transcode-next", response_class=HTMLResponse)
async def api_add_transcode_next(request: Request, payload: TranscodeNextPayload):
    """Inserts a job into Transcode Next list at a target position index."""
    insert_into_transcode_next(payload.job_id, payload.target_pos)
    return await render_queues_fragment(request)

@app.post("/api/jobs/{id}/append-transcode-next", response_class=HTMLResponse)
async def api_append_transcode_next(request: Request, id: int):
    """Pushes a pending job to the end of the Transcode Next queue."""
    add_to_transcode_next(id)
    return await render_queues_fragment(request)

@app.delete("/api/jobs/transcode-next/{id}", response_class=HTMLResponse)
async def api_remove_transcode_next(request: Request, id: int):
    """Removes a job from Transcode Next back to standard priority list."""
    remove_from_transcode_next(id)
    return await render_queues_fragment(request)

@app.post("/api/jobs/{id}/cancel", response_class=HTMLResponse)
async def api_cancel_job(request: Request, id: int):
    """Cancels a running or pending transcoding job."""
    cancel_running_job(id)
    return await render_queues_fragment(request)

@app.post("/api/jobs/{id}/delete", response_class=HTMLResponse)
async def api_delete_job(request: Request, id: int):
    """Deletes job from database history."""
    delete_job(id)
    return await render_queues_fragment(request)

@app.post("/api/queue/start", response_class=HTMLResponse)
async def api_start_queue(request: Request):
    """Resume workers queues execution loop."""
    resume_queue()
    return await render_queues_fragment(request)

@app.post("/api/queue/pause", response_class=HTMLResponse)
async def api_pause_queue(request: Request):
    """Pause workers queues execution loop."""
    pause_queue()
    return await render_queues_fragment(request)

@app.get("/api/jobs/poll-queues", response_class=HTMLResponse)
async def api_poll_queues(request: Request):
    """Polled by HTMX every few seconds to refresh running/pending tables with live status updates."""
    return await render_queues_fragment(request)

async def render_queues_fragment(request: Request) -> HTMLResponse:
    """Helper to return rendered queues fragment for HTMX updates."""
    jobs = get_jobs()
    pending = [j for j in jobs if j["status"] == "pending"]
    running = [j for j in jobs if j["status"] == "running"]
    completed = [j for j in jobs if j["status"] == "completed"]
    failed = [j for j in jobs if j["status"] == "failed"]
    cancelled = [j for j in jobs if j["status"] == "cancelled"]
    
    # Inject live progress details
    for run_job in running:
        progress_data = get_running_progress(run_job["id"])
        if progress_data:
            run_job.update(progress_data)
            
    transcode_next = [j for j in pending if j["transcode_next_position"] is not None]
    normal_queue = [j for j in pending if j["transcode_next_position"] is None]
    
    return templates.TemplateResponse(request, "components/queues_list.html", {
        "transcode_next": transcode_next,
        "normal_queue": normal_queue,
        "running": running,
        "history": completed + failed + cancelled,
        "queue_paused": is_queue_paused()
    })

# API ENDPOINTS - SYSTEM SETTINGS

@app.post("/api/settings", response_class=HTMLResponse)
async def api_save_settings(
    request: Request,
    recovery_action: str = Form("mark_failed_pause"),
    privacy_mode: bool = Form(False)
):
    """Updates database configuration variables."""
    set_setting("on_startup_orphaned_job_action", recovery_action)
    set_setting("privacy_mode_enabled", privacy_mode)
    
    # Return form with success message badge
    return templates.TemplateResponse(request, "components/settings_form.html", {
        "on_startup_orphaned_job_action": recovery_action,
        "privacy_mode_enabled": privacy_mode,
        "appdata_path": str(Path(os.getenv("EBRAKE_APPDATA_DIR", "./appdata")).resolve()),
        "media_path": str(MEDIA_DIR),
        "success_msg": "Settings saved successfully."
    })

# API ENDPOINTS - STANDALONE DRY-RUN TOOLS

@app.post("/api/tools/dedup", response_class=HTMLResponse)
async def api_tool_dedup(request: Request, file_path: str = Form(...)):
    """Triggers FPS Deduplication scanning on input."""
    p = Path(file_path)
    if not p.exists():
        return "<div class='alert alert-danger'>File not found.</div>"
        
    try:
        results = run_dedup_dryrun(p)
        return templates.TemplateResponse(request, "components/tool_dedup_result.html", {
            "results": results
        })
    except Exception as e:
        return f"<div class='alert alert-danger'>Deduplication scan failed: {e}</div>"

@app.post("/api/tools/vmaf-autocrf", response_class=HTMLResponse)
async def api_tool_vmaf_autocrf(
    request: Request,
    file_path: str = Form(...),
    vmaf_model: str = Form("1080p"),
    codec: str = Form(...),
    preset_val: str = Form(...),
    crf: int = Form(...),
    visual_tune: int = Form(0),
    fps: str = Form("same as source"),
    fps_mode: str = Form("constant"),
    pixel_format: str = Form("yuv420p"),
    target_vmaf: float = Form(0.0),
    vmaf_min: int = Form(18),
    vmaf_max: int = Form(30),
    dedup: bool = Form(False),
    passthrough_codecs: List[str] = Form([]),
    fallback_codec: str = Form("aac"),
    fallback_bitrate: int = Form(192000),
    sub_mode: str = Form("none"),
    burn_in_track_select: str = Form("default"),
    output_suffix: str = Form(""),
    container: str = Form("mkv")
):
    from app.engine import escape_filter_path
    p = Path(file_path)
    if not p.exists():
        return "<div class='alert alert-danger'>File not found.</div>"
        
    try:
        meta = probe_video(p)
        duration = meta["duration"]
        
        # Prepare filters (e.g. mpdecimate)
        vf_filters = []
        if dedup:
            vf_filters.append("mpdecimate=max=0:hi=64:lo=64:frac=0.001")
            
        burn_in_track = None
        if sub_mode == "burn-in":
            tracks = meta["subtitles"]
            if burn_in_track_select.isdigit():
                burn_in_track_idx = int(burn_in_track_select)
                burn_in_track = next((t for t in tracks if t["index"] == burn_in_track_idx), None)
            elif burn_in_track_select == "forced":
                burn_in_track = next((t for t in tracks if t["is_forced"]), None)
            if not burn_in_track:
                burn_in_track = next((t for t in tracks if t["is_default"]), None)
                if not burn_in_track and tracks:
                    burn_in_track = tracks[0]
            
            if burn_in_track:
                t_codec = burn_in_track["codec"]
                t_track_id = burn_in_track["track_id"]
                if "pgs" in t_codec or "dvd" in t_codec or "vob" in t_codec:
                    pass
                else:
                    escaped_input = escape_filter_path(p)
                    vf_filters.append(f"subtitles='{escaped_input}':si={t_track_id}")
                    
        vf_string = ",".join(vf_filters) if vf_filters else None
        
        active_target_vmaf = target_vmaf if target_vmaf > 0 else 95.0
        
        optimal_crf = run_vmaf_search(
            input_path=p,
            codec=codec,
            preset=preset_val,
            pix_fmt=pixel_format,
            filters=vf_string,
            target_vmaf=active_target_vmaf,
            crf_range=(vmaf_min, vmaf_max),
            duration=duration,
            use_mpdecimate=dedup,
            model_type=vmaf_model,
            video_width=meta.get("width", 1920),
            video_height=meta.get("height", 1080)
        )
        
        return templates.TemplateResponse(request, "components/tool_vmaf_autocrf_result.html", {
            "optimal_crf": optimal_crf,
            "target_vmaf": active_target_vmaf,
            "codec": codec,
            "preset": preset_val,
            "vmaf_model": vmaf_model
        })
    except Exception as e:
        logger.error(f"VMAF Auto-CRF scan failed: {e}", exc_info=True)
        return f"<div class='alert alert-danger'>VMAF Auto-CRF scan failed: {e}</div>"

@app.post("/api/tools/vmaf-compare", response_class=HTMLResponse)
async def api_tool_vmaf_compare(
    request: Request,
    ref_path: str = Form(...),
    dist_path: str = Form(...),
    vmaf_model: str = Form("1080p"),
    compare_mode: str = Form("full"),
    start_time: float = Form(0.0),
    duration: float = Form(10.0),
    dedup: bool = Form(False)
):
    ref_p = Path(ref_path)
    dist_p = Path(dist_path)
    if not ref_p.exists():
        return "<div class='alert alert-danger'>Reference file not found.</div>"
    if not dist_p.exists():
        return "<div class='alert alert-danger'>Distorted file not found.</div>"
        
    try:
        ref_meta = probe_video(ref_p)
        ref_duration = ref_meta["duration"]
        
        if compare_mode == "full":
            vmaf_score = run_vmaf_comparison(
                ref_path=ref_p,
                dist_path=dist_p,
                start_time=0.0,
                duration=ref_duration,
                use_mpdecimate=dedup,
                model_type=vmaf_model,
                video_width=ref_meta.get("width", 1920),
                video_height=ref_meta.get("height", 1080)
            )
            vmaf_duration = ref_duration
            vmaf_start = 0.0
        elif compare_mode == "segment":
            vmaf_score = run_vmaf_comparison(
                ref_path=ref_p,
                dist_path=dist_p,
                start_time=start_time,
                duration=duration,
                use_mpdecimate=dedup,
                model_type=vmaf_model,
                video_width=ref_meta.get("width", 1920),
                video_height=ref_meta.get("height", 1080)
            )
            vmaf_duration = duration
            vmaf_start = start_time
        else: # sampled
            timestamps = [ref_duration * 0.2, ref_duration * 0.5, ref_duration * 0.8]
            timestamps = [t for t in timestamps if t + 10.0 < ref_duration]
            if not timestamps:
                timestamps = [0.0]
                
            scores = []
            for ts in timestamps:
                score = run_vmaf_comparison(
                    ref_path=ref_p,
                    dist_path=dist_p,
                    start_time=ts,
                    duration=10.0,
                    use_mpdecimate=dedup,
                    model_type=vmaf_model,
                    video_width=ref_meta.get("width", 1920),
                    video_height=ref_meta.get("height", 1080)
                )
                scores.append(score)
            vmaf_score = sum(scores) / len(scores) if scores else 0.0
            vmaf_duration = len(timestamps) * 10.0
            vmaf_start = None
            
        return templates.TemplateResponse(request, "components/tool_vmaf_compare_result.html", {
            "vmaf_score": vmaf_score,
            "vmaf_model": vmaf_model,
            "compare_mode": compare_mode,
            "vmaf_start": vmaf_start,
            "vmaf_duration": vmaf_duration,
            "ref_name": ref_p.name,
            "dist_name": dist_p.name
        })
    except Exception as e:
        logger.error(f"VMAF Comparison failed: {e}", exc_info=True)
        return f"<div class='alert alert-danger'>VMAF Comparison failed: {e}</div>"
