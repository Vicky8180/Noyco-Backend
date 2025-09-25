#!/bin/bash
# API Gateway Startup Script
# Ensures JWT keys exist before starting the service

echo "🔑 Checking JWT keys..."

# Check if keys exist
if [ ! -f "/app/keys/private_key.pem" ] || [ ! -f "/app/keys/public_key.pem" ]; then
    echo "🔑 JWT keys not found, generating new ones..."
    python /app/generate_keys.py --key-dir /app/keys
    echo "✅ JWT keys generated successfully"
else
    echo "✅ JWT keys found"
fi

# Start the API Gateway
echo "🚀 Starting API Gateway..."
exec python -m uvicorn api_gateway.main:socket_app --host 0.0.0.0 --port 8080