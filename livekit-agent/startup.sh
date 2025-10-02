#!/bin/bash
# Startup script for LiveKit Agent with health check server

set -e

echo "🚀 Starting Noyco LiveKit Agent Service..."
echo "📍 Port: ${PORT:-8080}"
echo "🌐 Environment: ${ENVIRONMENT:-production}"

# Check required environment variables
if [ -z "$LIVEKIT_URL" ]; then
    echo "⚠️  Warning: LIVEKIT_URL not set"
fi

if [ -z "$LIVEKIT_API_KEY" ]; then
    echo "⚠️  Warning: LIVEKIT_API_KEY not set"
fi

if [ -z "$LIVEKIT_API_SECRET" ]; then
    echo "⚠️  Warning: LIVEKIT_API_SECRET not set"
fi

echo "✅ Starting server..."
exec python -u server.py start
