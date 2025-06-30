#!/bin/bash

# -------------------------------
# Script: start.sh
# Purpose: Start FastAPI backend
# Author: Chaoran Chen
# -------------------------------

# Export environment variables (if .env exists)
if [ -f ".env" ]; then
  echo "🌱 Loading .env variables..."
  export $(cat .env | grep -v '^#' | xargs)
fi

# Run server
echo "🚀 Starting FastAPI server on http://localhost:8000"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
