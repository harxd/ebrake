from flask import Flask, render_template, jsonify, request
import os
import sqlite3
import threading
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from config_loader import ConfigLoader
from transcoder import Transcoder

import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(process)d/%(threadName)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ebrake')

app = Flask(__name__)
config_mgr = ConfigLoader()
transcoder = Transcoder()

def get_media_base():
    base = os.path.abspath('/media')
    if not os.path.exists(base):
        base = os.path.join(os.getcwd(), 'media')
        os.makedirs(base, exist_ok=True)
    return base

# Ensure absolute paths for database
APPDATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "appdata")
DB_PATH = os.path.join(APPDATA_DIR, "jobs.db")

def init_db():
    os.makedirs("appdata", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_path TEXT,
            output_path TEXT,
            profile_name TEXT,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0,
            error TEXT,
            input_size INTEGER,
            output_size INTEGER,
            duration TEXT,
            command TEXT,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
    """)
    # Ensure new columns exist for existing databases
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN duration TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN command TEXT")
    except: pass
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN finished_at TIMESTAMP")
    except: pass
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN config TEXT")
    except: pass
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"CRITICAL: Failed to initialize database in appdata/. Check permissions! Error: {e}")
    # Don't exit here, let gunicorn logs capture it, but it will likely crash anyway


# File System Watcher
media_version = 0
def increment_media_version():
    global media_version
    media_version += 1

class MediaChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        increment_media_version()

observer = Observer()
try:
    observer.schedule(MediaChangeHandler(), get_media_base(), recursive=True)
    observer.start()
except Exception as e:
    print(f"Watcher failed to start: {e}")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Background Worker
def worker():
    logger.info("Background worker started")
    while True:
        db = get_db()
        job_id = None
        try:
            # Use a transaction to atomically check and claim a job
            db.execute("BEGIN IMMEDIATE")
            
            # Check if any job is currently running
            running = db.execute("SELECT id FROM jobs WHERE status = 'running'").fetchone()
            if running:
                logger.info(f"Worker skipping: Job {running['id']} is currently running")
                db.rollback()
                db.close()
                time.sleep(2)
                continue
            
            # Pick the next pending job
            job = db.execute("SELECT id FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1").fetchone()
            if not job:
                db.rollback()
                db.close()
                time.sleep(2)
                continue
            
            job_id = job['id']
            # Claim the job
            db.execute("UPDATE jobs SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
            db.commit()
            
            logger.info(f"Claimed job {job_id}")
            
            # Fetch full job data for processing
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            db.close()
        except Exception as e:
            logger.error(f"Worker loop error during claim: {e}")
            try: db.rollback()
            except: pass
            db.close()
            time.sleep(1)
            continue

        try:
            logger.info(f"Starting transcoding for job {job_id}: {job['input_path']}")
            # Load configuration
            import json
            profile_cfg = {}
            if job['config']:
                flat_cfg = json.loads(job['config'])
                # Nest the flat config for the transcoder
                profile_cfg = {'video': {}, 'audio': {}, 'output': {}}
                for k, v in flat_cfg.items():
                    if k.startswith('video_'): profile_cfg['video'][k[6:]] = v
                    elif k.startswith('audio_'): profile_cfg['audio'][k[6:]] = v
                    elif k.startswith('output_'): profile_cfg['output'][k[7:]] = v
                    else: profile_cfg[k] = v
            else:
                # Fallback to profile file (legacy)
                profile_content = config_mgr.read_profile(job['profile_name'])
                if not profile_content:
                    raise Exception(f"Profile {job['profile_name']} not found")
                
                current_section = ""
                for line in profile_content.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    if line.startswith('[') and line.endswith(']'):
                        current_section = line[1:-1]
                        profile_cfg[current_section] = {}
                    elif '=' in line:
                        k, v = line.split('=', 1)
                        val = v.strip().strip('"')
                        if current_section: profile_cfg[current_section][k.strip()] = val
                        else: profile_cfg[k.strip()] = val

            def update_progress(p):
                wdb = get_db()
                wdb.execute("UPDATE jobs SET progress = ? WHERE id = ?", (p, job_id))
                wdb.commit()
                wdb.close()

            # Resolve real path
            base_media = get_media_base()
            
            # Resolve Input
            rel_input = job['input_path']
            if rel_input.startswith('/media/'): rel_input = rel_input[7:]
            elif rel_input.startswith('/media'): rel_input = rel_input[6:]
            real_input_path = os.path.join(base_media, rel_input)
            
            # Record metadata and command
            input_size = os.path.getsize(real_input_path)
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(job['output_path']), exist_ok=True)

            cmd = transcoder.build_command(real_input_path, job['output_path'], profile_cfg)
            cmd_str = " ".join(cmd)

            wdb = get_db()
            wdb.execute("UPDATE jobs SET input_size = ?, command = ? WHERE id = ?", 
                       (input_size, cmd_str, job_id))
            wdb.commit()
            wdb.close()

            success, error_log = transcoder.run(cmd, update_progress)

            fdb = get_db()
            if success:
                logger.info(f"Job {job_id} completed successfully")
                output_size = os.path.getsize(job['output_path'])
                fdb.execute("UPDATE jobs SET status = 'completed', progress = 100, output_size = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?", (output_size, job_id))
            else:
                logger.error(f"Job {job_id} failed: {error_log}")
                fdb.execute("UPDATE jobs SET status = 'failed', error = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?", (error_log, job_id))
            fdb.commit()
            fdb.close()

        except Exception as e:
            logger.error(f"Fatal error in worker processing job {job_id}: {e}")
            fdb = get_db()
            fdb.execute("UPDATE jobs SET status = 'failed', error = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?", (str(e), job_id))
            fdb.commit()
            fdb.close()

if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    threading.Thread(target=worker, daemon=True).start()

@app.route('/')
@app.route('/create')
@app.route('/jobs')
@app.route('/profiles')
@app.route('/settings')
def index():
    return render_template('index.html')

@app.route('/api/files')
def list_files():
    base_dir = get_media_base()
    rel_path = request.args.get('path', '')
    target_dir = os.path.join(base_dir, rel_path)
    if not os.path.commonpath([base_dir, os.path.abspath(target_dir)]) == base_dir:
        return jsonify({'error': 'Access denied'}), 403

    try:
        items = []
        for name in os.listdir(target_dir):
            path = os.path.join(target_dir, name)
            is_dir = os.path.isdir(path)
            items.append({
                'name': name,
                'path': os.path.relpath(path, base_dir),
                'is_dir': is_dir,
                'size': os.path.getsize(path) if not is_dir else None
            })
        return jsonify({'items': sorted(items, key=lambda x: (not x['is_dir'], x['name']))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    db = get_db()
    jobs = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    db.close()
    
    res = []
    for j in jobs:
        d = dict(j)
        if d.get('input_size') and d.get('output_size'):
            savings = (1 - (d['output_size'] / d['input_size'])) * 100
            d['savings'] = f"{savings:.1f}%"
        else:
            d['savings'] = "-"
        res.append(d)
    return jsonify(res)

@app.route('/api/jobs/clear', methods=['POST'])
def clear_jobs():
    status = request.json.get('status') if request.is_json else None
    db = get_db()
    if status:
        db.execute("DELETE FROM jobs WHERE status = ?", (status,))
    else:
        db.execute("DELETE FROM jobs")
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/jobs/add', methods=['POST'])
def add_job():
    data = request.json
    input_paths = data.get('input_paths')
    if not input_paths:
        input_path = data.get('input_path')
        input_paths = [input_path] if input_path else []
    
    if not input_paths:
        return jsonify({'error': 'No input paths provided'}), 400

    # Default output dir from settings
    settings = config_mgr.get_settings()
    out_dir_setting = settings.get('output_dir', '')
    
    base_media = get_media_base()
    profile_name = data.get('profile_path')
    config = data.get('config') # Full JSON config from UI
    import json
    config_json = json.dumps(config) if config else None

    db = get_db()
    for input_path in input_paths:
        # If out_dir is empty, use source dir
        if not out_dir_setting:
            # Resolve real input path to find its directory
            rel_input = input_path
            if rel_input.startswith('/media/'): rel_input = rel_input[7:]
            elif rel_input.startswith('/media'): rel_input = rel_input[6:]
            real_input_path = os.path.join(base_media, rel_input)
            out_dir = os.path.dirname(real_input_path)
        else:
            out_dir = os.path.abspath(out_dir_setting)

        # Determine output filename
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        
        # We should use the extension from the config or profile
        ext = ".mkv"
        if config and config.get('output_container'):
            ext = "." + config['output_container']
        
        output_path = os.path.join(out_dir, base_name + ext)

        db.execute("INSERT INTO jobs (input_path, output_path, profile_name, config) VALUES (?, ?, ?, ?)",
                   (input_path, output_path, profile_name, config_json))
    
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/profiles')
def get_profiles():
    return jsonify({'tree': config_mgr.get_profile_tree()})

@app.route('/api/profiles/read')
def read_profile():
    rel_path = request.args.get('path', '')
    content = config_mgr.read_profile(rel_path)
    if content is None: return jsonify({'error': 'Not found'}), 404
    return jsonify({'content': content})

@app.route('/api/profiles/save', methods=['POST'])
def save_profile():
    data = request.json
    config_mgr.save_profile(data.get('path'), data.get('config', {}))
    return jsonify({'success': True})

@app.route('/api/profiles/create-dir', methods=['POST'])
def create_dir():
    data = request.json
    config_mgr.create_dir(data.get('parent', ''), data.get('name', ''))
    return jsonify({'success': True})

@app.route('/api/profiles/create-file', methods=['POST'])
def create_file():
    data = request.json
    config_mgr.create_file(data.get('parent', ''), data.get('name', ''))
    return jsonify({'success': True})

@app.route('/api/profiles/delete', methods=['POST'])
def delete_profile():
    data = request.json
    config_mgr.delete_path(data.get('path', ''))
    return jsonify({'success': True})

@app.route('/api/profiles/move', methods=['POST'])
def move_profile():
    data = request.json
    config_mgr.move_path(data.get('src', ''), data.get('dest', ''))
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        config_mgr.save_settings(request.json)
        return jsonify({'success': True})
    return jsonify(config_mgr.get_settings())

@app.route('/api/files/version')
def get_media_version():
    return jsonify({'version': media_version})

if __name__ == '__main__':
    logger.info("Starting ebrake application...")
    app.run(debug=True, port=5000)
