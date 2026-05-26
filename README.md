# ebrake
ffmpeg-based transcoding web app

### Stack
- **Backend**: FastAPI + Uvicorn
- **Frontend**: HTMX + Alpine.js / CSS
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