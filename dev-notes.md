# Docker Hub Workflow
```bash
# Build and push multi-arch (AMD64 + ARM64)
docker buildx build --platform linux/amd64,linux/arm64 -t minutelight/ebrake:latest --push .
```

# SQLite schema
Jobs

column | type | description
-------|------|------------
id | INTEGER | primary key
status | TEXT | `pending`, `running`, `completed`, `failed`, `cancelled`
created_at | DATETIME | when job was created
updated_at | DATETIME | when job was updated
started_at | DATETIME | when job was started
finished_at | DATETIME | when job was finished
duration | INTEGER | time it took to complete in seconds
savings | INTEGER | space saved in percentage
input_path | TEXT | input file path
output_path | TEXT | output file path
priority | INTEGER | job priority
category | TEXT | name of the preset category
preset | TEXT | name of the .ebrake preset used
error | TEXT | error message

# .ebrake presets
`/category/preset.ebrake`
```toml
name = "Standard 1080p"
description = "Standard 1080p preset"
extension = "mp4"

[video]
codec = "libx264"
crf = 23
preset = "medium"
args = ["-movflags", "+faststart"]

[audio]
codec = "aac"
bitrate = "128k"
passthrough = ["ac3", "eac3", "dts", "flac"]
```

# General Config
`ebrake.toml`
```toml
default_preset = "Standard/1080p.ebrake"

[ui]
privacy_mode = false  # obfuscate paths/names
```