from flask import Flask, render_template, jsonify, request
import os
from config_loader import ConfigLoader

app = Flask(__name__)
config = ConfigLoader()

@app.route('/')
@app.route('/create')
@app.route('/jobs')
@app.route('/profiles')
@app.route('/settings')
def index():
    return render_template('index.html')

@app.route('/api/files')
def list_files():
    # Base directory for the file browser
    base_dir = os.path.abspath('/media')
    
    # On Windows, /media might not exist, so let's use a dummy path if it's missing for dev
    if not os.path.exists(base_dir):
        base_dir = os.path.join(os.getcwd(), 'media')
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

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

@app.route('/api/profiles')
def get_profiles():
    try:
        return jsonify({'tree': config.get_profile_tree()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/read')
def read_profile():
    rel_path = request.args.get('path', '')
    try:
        content = config.read_profile(rel_path)
        if content is None: return jsonify({'error': 'Not found'}), 404
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/save', methods=['POST'])
def save_profile():
    data = request.json
    path = data.get('path')
    payload = data.get('config', {})
    if not path: return jsonify({'error': 'Path required'}), 400
    try:
        config.save_profile(path, payload)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/create-dir', methods=['POST'])
def create_dir():
    data = request.json
    try:
        config.create_dir(data.get('parent', ''), data.get('name', ''))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/create-file', methods=['POST'])
def create_file():
    data = request.json
    try:
        config.create_file(data.get('parent', ''), data.get('name', ''))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/delete', methods=['POST'])
def delete_profile():
    data = request.json
    try:
        config.delete_path(data.get('path', ''))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profiles/move', methods=['POST'])
def move_profile():
    data = request.json
    try:
        config.move_path(data.get('src', ''), data.get('dest', ''))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
