#!/bin/bash

# Start Celery Worker for Convis Workflows
# This script starts the Celery worker that processes delayed workflow actions

echo "=========================================="
echo "🚀 Starting Celery Worker"
echo "=========================================="
echo ""

# Check if Redis is running
echo "Checking Redis connection..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✓ Redis is running"
else
    echo "✗ Redis is not running. Starting Redis..."
    if command -v redis-server &> /dev/null; then
        redis-server --daemonize yes
        echo "✓ Redis started"
    else
        echo "✗ Redis not installed. Please install Redis:"
        echo "  macOS: brew install redis"
        echo "  Ubuntu: sudo apt-get install redis-server"
        exit 1
    fi
fi

echo ""
echo "Starting Celery worker..."
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start Celery worker with auto-reload for development
celery -A app.config.celery_config:celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=workflows,actions,default \
    --pool=solo

# Note: Use --pool=solo for development on macOS
# For production, use: --pool=prefork --concurrency=4
