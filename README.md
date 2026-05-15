# ebrake
Simple ffmpeg-based transcoding web app.

> AI has been used in the development of this app

### Stack
- **Backend**: Flask (Python 3.11)
- **Frontend**: Vanilla JS / CSS (Modern UI with Outfit & JetBrains Mono)
- **Engine**: FFmpeg (handles all transcoding tasks)
- **Database**: SQLite (local job tracking)
- **Presets**: `.ebrake` (TOML-based) profiles

### Quick Start with Docker

```yaml
services:
  ebrake:
    image: minutelight/ebrake:latest
    container_name: ebrake
    ports:
      - "5000:5000"
    volumes:
      # PERSISTENT DATA: Keep your database, profiles, and settings safe
      - ./appdata:/app/appdata
      
      # MEDIA ACCESS: Path to your movies/videos
      - /path/to/your/media:/media:rw
      
    restart: unless-stopped
    environment:
      - TZ=UTC
```

### Rootless Podman (Quadlet)
For users running Podman on Linux (e.g., Fedora, RHEL), Quadlets provide the best systemd integration. Create `~/.config/containers/systemd/ebrake.container`:

```ini
[Unit]
Description=ebrake Transcoding Service

[Container]
Image=minutelight/ebrake:latest
ContainerName=ebrake
PublishPort=5000:5000
Volume=%h/ebrake/appdata:/app/appdata:Z
Volume=%h/Videos:/media:rw,z

[Service]
Restart=always

[Install]
WantedBy=default.target
```
Run `systemctl --user daemon-reload && systemctl --user start ebrake` to deploy.


### Local Development

1. Create a virtual environment: `python -m venv .venv`
2. Install dependencies: `.venv/Scripts/pip install -r requirements.txt gunicorn`
3. Run the app: `$env:PYTHONPATH="app"; .venv/Scripts/python.exe app/main.py`

### Future features

- VMAF