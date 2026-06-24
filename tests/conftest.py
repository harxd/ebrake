import os
import sys
import time
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
import pytest

@pytest.fixture(scope="session")
def sandbox_env():
    # Setup Sandbox Environment
    sandbox_dir = Path(tempfile.mkdtemp(prefix="ebrake_ui_test_")).resolve()
    appdata_dir = sandbox_dir / "appdata"
    media_dir = sandbox_dir / "media"
    
    # Copy fixtures into sandbox media
    project_root = Path(__file__).resolve().parent.parent
    fixtures_media_dir = project_root / "tests" / "fixtures" / "media"
    
    if fixtures_media_dir.exists():
        shutil.copytree(fixtures_media_dir, media_dir)
    else:
        media_dir.mkdir(parents=True)

    env = os.environ.copy()
    env["EBRAKE_APPDATA_DIR"] = str(appdata_dir)
    env["EBRAKE_MEDIA_DIR"] = str(media_dir)
    
    # Temporarily set env vars in current process as well so init_db uses correct paths
    os.environ["EBRAKE_APPDATA_DIR"] = str(appdata_dir)
    os.environ["EBRAKE_MEDIA_DIR"] = str(media_dir)
    
    # Add project_root to sys.path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        
    # Now we can safely import app modules to initialize DB
    from app.config import init_directories
    from app.database import init_db
    
    init_directories()
    init_db()

    yield env

    # Teardown
    if sandbox_dir.exists():
        try:
            shutil.rmtree(sandbox_dir)
        except PermissionError:
            pass # ignore Windows file locks on teardown

def wait_for_server(url, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url) as response:
                if response.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(0.5)
    return False

@pytest.fixture(scope="session")
def server_url(sandbox_env):
    project_root = Path(__file__).resolve().parent.parent
    port = "5002"
    url = f"http://127.0.0.1:{port}"

    print(f"\nStarting test Uvicorn server on port {port}...")
    server_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", port, "--log-level", "warning"
        ],
        cwd=str(project_root),
        env=sandbox_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if not wait_for_server(f"{url}/create-job", timeout=12):
        stdout, stderr = server_proc.communicate(timeout=1)
        print("--- Server Stdout ---", stdout, sep="\n", file=sys.stderr)
        print("--- Server Stderr ---", stderr, sep="\n", file=sys.stderr)
        server_proc.terminate()
        raise RuntimeError("Test server failed to start.")

    yield url

    print("\nShutting down test Uvicorn server...")
    server_proc.terminate()
    try:
        server_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server_proc.kill()
