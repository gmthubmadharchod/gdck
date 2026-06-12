#!/bin/bash

# Start Docker daemon
dockerd --host=unix:///var/run/docker.sock --host=tcp://0.0.0.0:2375 &
sleep 5

# Wait for Docker
while ! docker info > /dev/null 2>&1; do
    echo "Waiting for Docker..."
    sleep 1
done

echo "✅ Docker ready!"

# Run the bot
python app.py
