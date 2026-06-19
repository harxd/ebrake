# Use lightweight official Python image
FROM python:3.12-slim

# Install system dependencies (FFmpeg + FFprobe + fonts for subtitles)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy python packages requirements
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source directories and static assets
COPY app/ ./app/
COPY static/ ./static/

# Expose internal HTTP port
EXPOSE 5000

# Set environment variables for Docker volume paths
ENV EBRAKE_APPDATA_DIR=/app/appdata
ENV EBRAKE_MEDIA_DIR=/media
ENV PYTHONUNBUFFERED=1

# Command to run Uvicorn server on boot
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
