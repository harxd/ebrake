# ebrake
Simple ffmpeg-based transcoding web app.

> AI has been used in the development of this app

### Roadmap
- Search in the file manager
- Responsive design
- Duplicate frames detection
- VMAF

### Stack
- **Backend**: Flask
- **Frontend**: Vanilla JS / CSS
- **Engine**: FFmpeg
- **Database**: SQLite
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
      - ./appdata:/app/appdata
      - /path/to/your/media:/media:rw
    restart: unless-stopped
    environment:
      - TZ=UTC
```

### Rootless Podman (Quadlet)
Create `~/.config/containers/systemd/ebrake.container`:
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
Run `systemctl --user daemon-reload && systemctl --user start ebrake`


### Local Development

1. Create a virtual environment: `python -m venv .venv`
2. Install dependencies: `.venv/Scripts/pip install -r requirements.txt gunicorn`
3. Run the app: `.venv/Scripts/python.exe app/main.py`