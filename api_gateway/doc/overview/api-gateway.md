# API Gateway Service Documentation

## Overview
The API Gateway serves as the central entry point for all microservices in the healthcare platform. It handles authentication, routing, and provides a unified interface for all services.

## Features
- **Authentication & Authorization**: JWT-based authentication with middleware
- **Routing**: Centralized routing to all microservices
- **CORS Configuration**: Configurable cross-origin resource sharing
- **Health Monitoring**: Comprehensive health checks for all services
- **Socket.IO Integration**: Real-time communication support
- **Call Interface**: Real-time call management system

## Endpoints

### Core Endpoints
- `GET /` - Root endpoint with platform information
- `GET /health` - Simple health check
- `GET /health/services` - Comprehensive health check for all services

### Call Interface
- `POST /api/call` - Trigger incoming call
- `GET /api/calls/active` - Get all active calls

### Documentation
- `GET /docs/` - List all available documentation
- `GET /docs/{filename}` - Get documentation content as JSON
- `GET /docs/raw/{filename}` - Get raw markdown content
- `GET /docs/search/{query}` - Search through documentation

## Configuration
The service uses environment variables for configuration:
- `SERVICE_HOST` - Host to bind the service
- `SERVICE_PORT` - Port to run the service
- `ALLOWED_ORIGINS` - CORS allowed origins
- `JWT_SECRET_KEY` - Secret key for JWT tokens

## Usage Examples

### Health Check
```bash
curl -X GET "http://localhost:8000/health"
```

### Trigger Call
```bash
curl -X POST "http://localhost:8000/api/call"
```

### Get Documentation
```bash
curl -X GET "http://localhost:8000/docs/api-gateway"
```

## Dependencies
- FastAPI
- uvicorn
- python-socketio
- PyJWT
- Other microservice-specific dependencies

## Deployment
The service can be run using:
```bash
python -m uvicorn api_gateway.main:socket_app --host 0.0.0.0 --port 8000
```