from flask import Flask, render_template, jsonify, request
import os
import sqlite3
import threading
import time
from datetime import datetime
from config_loader import ConfigLoader
from transcoder import Transcoder

app = Flask(__name__)
config_mgr = ConfigLoader()
transcoder = Transcoder()

def get_media_base():
    base = os.path.abspath('/media')
    if not os.path.exists(base):
        base = os.path.join(os.getcwd(), 'media')
        os.makedirs(base, exist_ok=True)
    return base

DB_PATH = "appdata/jobs.db"

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP
        )
    """)
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Background Worker
def worker():
    while True:
        db = get_db()
        job = db.execute("SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1").fetchone()
        if not job:
            db.close()
            time.sleep(2)
            continue

        job_id = job['id']
        db.execute("UPDATE jobs SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?", (job_id,))
        db.commit()
        db.close()

        try:
            # Load profile for settings
            # We need to read the profile file
            profile_content = config_mgr.read_profile(job['profile_name'])
            if not profile_content:
                raise Exception(f"Profile {job['profile_name']} not found")
            
            # Simple TOML parser in Python for the worker
            profile_cfg = {}
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
            
            # Record input size
            input_size = os.path.getsize(real_input_path)
            wdb = get_db()
            wdb.execute("UPDATE jobs SET input_size = ? WHERE id = ?", (input_size, job_id))
            wdb.commit()
            wdb.close()

            # Ensure output directory exists
            os.makedirs(os.path.dirname(job['output_path']), exist_ok=True)

            cmd = transcoder.build_command(real_input_path, job['output_path'], profile_cfg)
            success, error_log = transcoder.run(cmd, update_progress)

            fdb = get_db()
            if success:
                output_size = os.path.getsize(job['output_path'])
                fdb.execute("UPDATE jobs SET status = 'completed', progress = 100, output_size = ? WHERE id = ?", (output_size, job_id))
            else:
                fdb.execute("UPDATE jobs SET status = 'failed', error = ? WHERE id = ?", (error_log, job_id))
            fdb.commit()
            fdb.close()

        except Exception as e:
            fdb = get_db()
            fdb.execute("UPDATE jobs SET status = 'failed', error = ? WHERE id = ?", (str(e), job_id))
            fdb.commit()
            fdb.close()

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
    db = get_db()
    db.execute("DELETE FROM jobs")
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/jobs/add', methods=['POST'])
def add_job():
    data = request.json
    input_path = data.get('input_path')
    # Default output dir from settings
    settings = config_mgr.get_settings()
    out_dir = settings.get('output_dir', '')
    
    base_media = get_media_base()
    
    # If out_dir is empty, use source dir
    if not out_dir:
        # Resolve real input path to find its directory
        rel_input = input_path
        if rel_input.startswith('/media/'): rel_input = rel_input[7:]
        elif rel_input.startswith('/media'): rel_input = rel_input[6:]
        real_input_path = os.path.join(base_media, rel_input)
        out_dir = os.path.dirname(real_input_path)
    else:
        out_dir = os.path.abspath(out_dir)

    # Determine output filename
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    # We should get container from profile, but for now use mkv or what's in data
    # Actually, the frontend should send the desired output path or we calculate it here
    
    # For now, let's assume the frontend sends the calculated output_path 
    # or we do it here based on the profile
    profile_name = data.get('profile_path') # This is the rel path to the profile
    
    # We'll just use the provided output_path if it exists, else generate one
    output_path = data.get('output_path')
    if not output_path:
        output_path = os.path.join(out_dir, base_name + ".mkv")

    db = get_db()
    db.execute("INSERT INTO jobs (input_path, output_path, profile_name) VALUES (?, ?, ?)",
               (input_path, output_path, profile_name))
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
