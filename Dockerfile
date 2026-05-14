# Use a Python 3.11 slim base image
FROM python:3.11-slim

# Install system dependencies
# We need ffmpeg for transcoding and other tools for SVT-AV1 support
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy the application code
COPY . .

# Create necessary directories
RUN mkdir -p /media /app/appdata

# Expose the application port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app/main.py
ENV PYTHONPATH=/app/app
ENV PYTHONUNBUFFERED=1

# Command to run the application
# Using gunicorn for better performance and stability
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app.main:app"]


