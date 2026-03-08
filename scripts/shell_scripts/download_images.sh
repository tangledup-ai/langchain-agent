#!/bin/bash
# Script to download and package Docker images for offline use
# Run this on a machine with good Docker Hub access, then transfer images.tar to China

set -e

echo "=== Docker Image Downloader for Offline Use ==="
echo ""

# Images needed
IMAGES=(
    "node:20-alpine"
    "python:3.12-slim"
    "postgres:16-alpine"
    "nginx:alpine"
)

OUTPUT_FILE="images.tar"

echo "Pulling Docker images..."
for img in "${IMAGES[@]}"; do
    echo "  Pulling $img..."
    docker pull "$img"
done

echo ""
echo "Saving to $OUTPUT_FILE..."
docker save "${IMAGES[@]}" -o "$OUTPUT_FILE"

echo ""
echo "Done! File size:"
ls -lh "$OUTPUT_FILE"

echo ""
echo "To transfer to China machine and load:"
echo "  scp images.tar user@china-machine:/path/"
echo "  docker load < images.tar"
