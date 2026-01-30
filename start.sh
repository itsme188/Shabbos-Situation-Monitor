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
echo "========================================"
echo ""

# Run the server
python3 server.py
