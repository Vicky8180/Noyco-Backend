# #!/bin/bash
# # Startup script for LiveKit Agent with health check server

# set -e

# echo "🚀 Starting Noyco LiveKit Agent Service..."
# echo "📍 Port: ${PORT:-8080}"
# echo "🌐 Environment: ${ENVIRONMENT:-production}"

# # Check required environment variables
# if [ -z "$LIVEKIT_URL" ]; then
#     echo "⚠️  Warning: LIVEKIT_URL not set"
# fi

# if [ -z "$LIVEKIT_API_KEY" ]; then
#     echo "⚠️  Warning: LIVEKIT_API_KEY not set"
# fi

# if [ -z "$LIVEKIT_API_SECRET" ]; then
#     echo "⚠️  Warning: LIVEKIT_API_SECRET not set"
# fi

# echo "✅ Starting server..."
# exec python -u server.py start


#!/bin/bash
# Multi-Tenant LiveKit Agent Startup Script
# This script starts the multi-tenant agent server

set -e

echo "🚀 Starting Multi-Tenant Noyco LiveKit Agent..."
echo "================================================"
echo ""

# Check if running in Cloud Run
if [ -n "$K_SERVICE" ]; then
    echo "✅ Running in Google Cloud Run"
    echo "   Service: $K_SERVICE"
    echo "   Revision: $K_REVISION"
    echo "   Configuration: $K_CONFIGURATION"
else
    echo "✅ Running locally"
fi

echo ""
echo "Configuration:"
echo "   Python: $(python --version)"
echo "   Port: ${PORT:-8080}"
echo "   Mode: Multi-Tenant"
echo ""

# Set Python to run in unbuffered mode for better logging
export PYTHONUNBUFFERED=1

# Start the multi-tenant server
echo "🎯 Launching multi-tenant server..."
exec python server.py start
