FROM python:3.10-slim

# Install Docker
RUN apt-get update && apt-get install -y \
    docker.io \
    tar \
    gzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static /tmp/docker_extract

# Start script
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
