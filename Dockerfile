FROM python:3.11-slim

# Set work directory
WORKDIR /app

# Set env variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies (optional, but good for pip updates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY src/ /app/src/
COPY specs/ /app/specs/
# Note: credentials key file (gcp_key.json) is usually mounted at runtime 
# or passed as env variable.

# Port for Cloud Run / HTTP Server
EXPOSE 8080

# Command to run on container start (starts HTTP server by default)
CMD ["python", "src/main.py", "--server"]
