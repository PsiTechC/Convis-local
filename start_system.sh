#!/bin/bash

# Convis System Startup Script
# Starts both frontend and backend servers

echo "========================================"
echo "🚀 Starting Convis System"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if backend API is running
echo -e "${YELLOW}Checking backend API...${NC}"
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${GREEN}✓ Backend API is already running on port 8000${NC}"
else
    echo -e "${YELLOW}Starting backend API...${NC}"
    cd convis-api

    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}Creating virtual environment...${NC}"
        python3 -m venv venv
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Install dependencies
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -q -r requirements.txt

    # Start backend in background
    echo -e "${YELLOW}Starting FastAPI server...${NC}"
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/convis-api.log 2>&1 &
    API_PID=$!
    echo -e "${GREEN}✓ Backend API started (PID: $API_PID)${NC}"
    echo -e "  Logs: tail -f /tmp/convis-api.log"

    cd ..
fi

echo ""

# Check if frontend is running
echo -e "${YELLOW}Checking frontend...${NC}"
if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${GREEN}✓ Frontend is already running on port 3000${NC}"
elif lsof -Pi :3001 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${GREEN}✓ Frontend is already running on port 3001${NC}"
else
    echo -e "${YELLOW}Starting frontend...${NC}"
    cd convis-web

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing npm dependencies...${NC}"
        npm install
    fi

    # Start frontend in background
    echo -e "${YELLOW}Starting Next.js server...${NC}"
    npm run dev > /tmp/convis-web.log 2>&1 &
    WEB_PID=$!
    echo -e "${GREEN}✓ Frontend started (PID: $WEB_PID)${NC}"
    echo -e "  Logs: tail -f /tmp/convis-web.log"

    cd ..
fi

echo ""
echo "========================================"
echo -e "${GREEN}✓ Convis System Started Successfully!${NC}"
echo "========================================"
echo ""
echo "📍 Access Points:"
echo "  - Frontend: http://localhost:3000"
echo "  - API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "📋 Logs:"
echo "  - Backend: tail -f /tmp/convis-api.log"
echo "  - Frontend: tail -f /tmp/convis-web.log"
echo ""
echo "🛑 To stop:"
echo "  - killall uvicorn"
echo "  - killall node"
echo ""
echo "📚 Documentation:"
echo "  - Workflow Guide: WORKFLOW_SYSTEM_GUIDE.md"
echo "  - Webhook Guide: WEBHOOK_TRIGGER_GUIDE.md"
echo "  - Feature Plan: MISSING_FEATURES_IMPLEMENTATION_PLAN.md"
echo ""
echo "⏳ Waiting for services to start (10 seconds)..."
sleep 10

# Test backend
echo -e "${YELLOW}Testing backend API...${NC}"
if curl -s http://localhost:8000/docs > /dev/null; then
    echo -e "${GREEN}✓ Backend API is responding${NC}"
else
    echo -e "${RED}✗ Backend API is not responding yet${NC}"
    echo -e "  Check logs: tail -f /tmp/convis-api.log"
fi

# Test frontend
echo -e "${YELLOW}Testing frontend...${NC}"
if curl -s http://localhost:3000 > /dev/null; then
    echo -e "${GREEN}✓ Frontend is responding on port 3000${NC}"
elif curl -s http://localhost:3001 > /dev/null; then
    echo -e "${GREEN}✓ Frontend is responding on port 3001${NC}"
else
    echo -e "${RED}✗ Frontend is not responding yet (may still be building)${NC}"
    echo -e "  Check logs: tail -f /tmp/convis-web.log"
fi

echo ""
echo -e "${GREEN}🎉 All set! Open http://localhost:3000 in your browser${NC}"
echo ""
