#!/bin/bash
# Development startup script - uses ngrok URL from .env file
# Unset production environment variables that may override .env file

unset API_BASE_URL
unset BASE_URL
unset CORS_ORIGINS
unset REDIS_URL
unset CELERY_BROKER_URL
unset CELERY_RESULT_BACKEND
unset ENVIRONMENT

# Kill existing server
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Wait for port to be released
sleep 2

# Start API server
echo "Starting API server in development mode..."
echo "Ngrok URL will be loaded from .env file"
python3 run.py
