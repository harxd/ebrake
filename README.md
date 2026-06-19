# ebrake
ffmpeg-based transcoding web app, distributed as Docker/Podman container.

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

---

## Development

### 1. Running Locally
To run the application locally on your host machine:

1. **Prerequisites**:
   Ensure you have Python 3.12+ and `ffmpeg`/`ffprobe` installed and available in your system path.
2. **Set Up Virtual Environment**:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
   source .venv/bin/activate
   
   pip install -r requirements.txt
   ```
3. **Run Automated Logic Verifications**:
   ```bash
   python verify.py
   ```
4. **Start Web Server**:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 5000
   ```
   Open `http://127.0.0.1:5000` in your browser.

### 2. Running via Docker
To build and run the application inside a container locally:

1. **Orchestrate Build**:
   ```bash
   docker compose up --build
   ```
   This builds the `Dockerfile` and mounts `./appdata` (presets/configurations) and `./media` (source videos).
2. **Access App**:
   Navigate to `http://localhost:5000`.

### 3. Pushing to Repository
To build the image and push it to the Docker Hub `minutelight/ebrake` registry:

1. **Authentication**:
   ```bash
   docker login
   ```
2. **Build and Tag Image**:
   ```bash
   docker build -t minutelight/ebrake:latest -t minutelight/ebrake:1.0.0 .
   ```
3. **Push Tags**:
   ```bash
   docker push minutelight/ebrake:latest
   docker push minutelight/ebrake:1.0.0
   ```