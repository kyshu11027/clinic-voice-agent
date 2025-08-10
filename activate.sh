#!/bin/bash

# Activate virtual environment and start development server
echo "Activating virtual environment..."
source venv/bin/activate

echo "Starting development server..."
echo "Server will be available at: http://localhost:8000"
echo "Health check: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
