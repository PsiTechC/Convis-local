#!/bin/bash
# Development startup script with ngrok
# This script sets the ngrok URL and starts the API server

# Kill existing server
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Wait for port to be released
sleep 2

# Export ngrok URL (this overrides any system environment variables)
export API_BASE_URL="https://3a9b688843f9.ngrok-free.app"
export BASE_URL="https://3a9b688843f9.ngrok-free.app"
export ENVIRONMENT="development"

# Unset production Redis and Celery URLs
unset REDIS_URL
unset CELERY_BROKER_URL
unset CELERY_RESULT_BACKEND
unset CORS_ORIGINS

# Start API server
echo "Starting API server in development mode with ngrok..."
echo "Ngrok URL: $API_BASE_URL"
python3 run.py
