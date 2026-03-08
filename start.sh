#!/bin/bash
# Shabbos Situation Monitor - Startup Script

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "   Shabbos Situation Monitor"
echo "========================================"
echo ""

# Navigate to script directory
cd "$(dirname "$0")"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${NC}"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment${NC}"
        exit 1
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.deps_installed" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        touch venv/.deps_installed
        echo -e "${GREEN}Dependencies installed successfully${NC}"
    else
        echo -e "${RED}Failed to install dependencies${NC}"
        exit 1
    fi
fi

# ---- Duplicate-instance guard ----
# Prevent multiple start.sh from running concurrently (root cause of Shabbos #2 failure)
EXISTING_PID=$(lsof -i :8080 -t 2>/dev/null)
if [ -n "$EXISTING_PID" ]; then
    echo -e "${RED}ERROR: Port 8080 already in use by PID $EXISTING_PID${NC}"
    echo -e "${YELLOW}Another instance is already running.${NC}"
    echo ""
    echo "To kill all existing instances and start fresh:"
    echo "  pkill -f 'start.sh' ; pkill -f 'server.py'"
    echo ""
    exit 1
fi

# Get local IP for easy access from other devices
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}Starting server...${NC}"
echo ""
echo "Access the monitor at:"
echo "  Local:   http://localhost:8080"
if [ -n "$LOCAL_IP" ]; then
    echo "  Network: http://${LOCAL_IP}:8080"
fi
echo ""
echo "Press Ctrl+C to stop the server"
echo "Server will auto-restart on crash."
echo "========================================"
echo ""

# Run the server with auto-restart on crash
# Ctrl+C (SIGINT) exits the loop cleanly via the trap
trap 'echo -e "\n${YELLOW}Shutting down...${NC}"; exit 0' INT TERM

while true; do
    python3 server.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}Server stopped cleanly.${NC}"
        break
    fi
    echo ""
    echo -e "${RED}Server exited with code $EXIT_CODE. Restarting in 5 seconds...${NC}"
    echo -e "${YELLOW}(Press Ctrl+C to stop)${NC}"
    sleep 5
    # Re-check port before restarting (another instance may have claimed it)
    EXISTING_PID=$(lsof -i :8080 -t 2>/dev/null)
    if [ -n "$EXISTING_PID" ]; then
        echo -e "${RED}Port 8080 now in use by PID $EXISTING_PID. Exiting restart loop.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Restarting server...${NC}"
    echo ""
done
