from flask import Flask, render_template, jsonify, request
import os

app = Flask(__name__)

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
        # For demonstration on windows, use a local 'media' folder in the project
        base_dir = os.path.join(os.getcwd(), 'media')
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)

    rel_path = request.args.get('path', '')
    target_dir = os.path.join(base_dir, rel_path)
    
    # Security check: ensure the target is within base_dir
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

if __name__ == '__main__':
    # Ensure static and templates are found correctly
    app.run(debug=True, port=5000)
