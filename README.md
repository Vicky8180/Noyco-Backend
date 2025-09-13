# ConversationalEngine

A comprehensive healthcare conversational AI platform built with a microservices architecture. This system provides intelligent medical conversation handling, real-time communication, memory management, and specialized medical agents.

## 🏗️ Architecture Overview

The ConversationalEngine is built as a distributed microservices platform that orchestrates multiple specialized AI agents to handle medical conversations intelligently. The system is designed for scalability, real-time processing, and healthcare-grade reliability.

### Core Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Gateway   │────│   Orchestrator   │────│     Memory      │
│    (Port 8000)  │    │   (Port 8002)    │    │  (Port 8010)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                        │
         │              ┌─────────┴─────────┐              │
         │              │                   │              │
         ▼              ▼                   ▼              ▼
┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│   Checkpoint    │  │   Specialists    │  │     Common      │
│  (Port 8003)    │  │  (Multiple Ports)│  │   Services      │
└─────────────────┘  └──────────────────┘  └─────────────────┘
```

## 🚀 Services

### 1. **API Gateway** (Port 8000)
- **Purpose**: Main entry point for all external requests
- **Features**: 
  - Authentication & authorization (JWT)
  - Request routing to appropriate microservices
  - Real-time communication via Socket.IO
  - CORS handling
  - Health monitoring
  - Call interface for real-time interactions
- **Key Files**: `api_gateway/main.py`, `api_gateway/router_config.py`

### 2. **Orchestrator** (Port 8002)
- **Purpose**: Central coordination hub for conversation flow
- **Features**:
  - Task orchestration and workflow management
  - Agent coordination and load balancing
  - Conversation state management

  - Timing metrics and performance monitoring
- **Key Files**: `orchestrator/main.py`, `orchestrator/services.py`

### 3. **Memory Service** (Port 8010)
- **Purpose**: Ultra-low latency memory management and storage
- **Features**:
  - Redis integration for fast caching
  - MongoDB for persistent storage
  - Pinecone vector database for semantic search
  - TTL caching with performance optimizations
  - Thread pool for CPU-bound operations
- **Key Files**: `memory/main.py`, `memory/redis_client.py`

### 4. **Checkpoint Service** (Port 8003)
- **Purpose**: Medical conversation checkpoint generation
- **Features**:
  - Conversation flow checkpointing
  - Task progress tracking
  - Integration with Gemini AI for intelligent checkpointing
- **Key Files**: `checkpoint/main.py`, `checkpoint/generator.py`

### 5. **Specialist Services**

#### Primary Specialist (Port 8004)
- General medical conversation handling
- Primary care decision making
- Patient interaction management

#### Checklist Specialist (Port 8007)
- Medical checklist generation and validation
- Procedure compliance checking
- Quality assurance for medical processes

#### Agents Specialist (Port 8015)
- Specialized AI agents (loneliness, mental health, etc.)
- Multi-agent coordination
- Streaming response capabilities

## 🛠️ Technology Stack

### Backend Framework
- **FastAPI**: High-performance async web framework
- **Uvicorn**: ASGI server for production deployment
- **Socket.IO**: Real-time bidirectional communication

### AI & Machine Learning
- **Google Gemini AI**: Advanced language model integration
- **Google Cloud Speech**: Speech-to-text processing
- **Google Cloud Text-to-Speech**: Voice synthesis
- **Google Cloud Vision**: OCR and image processing

### Database & Storage
- **MongoDB**: Primary database for persistent storage
- **Redis**: High-speed caching and session storage
- **Pinecone**: Vector database for semantic search

### Authentication & Security
- **JWT**: JSON Web Token authentication
- **bcrypt**: Password hashing
- **CSRF Protection**: Cross-site request forgery protection
- **CORS**: Cross-origin resource sharing

### Communication & Integration
- **httpx**: Async HTTP client for service communication
- **WebSockets**: Real-time bidirectional communication
- **Deepgram SDK**: Advanced speech processing

## 📋 Prerequisites

- **Python 3.11+**
- **MongoDB**: Local or cloud instance
- **Redis**: Local or cloud instance
- **Google Cloud Account**: For AI services
- **Pinecone Account**: For vector database (optional)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
cd conversationalEngine
```

### 2. Environment Configuration

Create a `.env` file with the following configuration:

```bash
# Environment
ENVIRONMENT=development

# Security - JWT
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_PRIVATE_KEY_PATH=./keys/private_key.pem
JWT_PUBLIC_KEY_PATH=./keys/public_key.pem
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Database connections
MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=conversionalEngine
REDIS_URL=redis://localhost:6379

# Google Cloud AI Services
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_CLOUD_PROJECT_ID=your_project_id

# Optional: Vector Database
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENVIRONMENT=your_pinecone_environment

# CORS Settings
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
```

### 3. Install Dependencies

```bash
pip install -r requirements3.txt
```

### 4. Generate Security Keys

```bash
python generate_keys.py
```

### 5. Start All Services

#### Development Mode (with auto-reload)
```bash
python run_dev.py --dev
```

#### Production Mode
```bash
python run_dev.py
```

#### Start Individual Services
```bash
# API Gateway only
python run_dev.py --service api_gateway

# Orchestrator only
python run_dev.py --service orchestrator

# Memory service only
python run_dev.py --service memory
```

## 🔧 Service Configuration

### Port Configuration
- **API Gateway**: 8000 (Socket.IO enabled)
- **Orchestrator**: 8002
- **Checkpoint**: 8003
- **Primary Specialist**: 8004
- **Checklist Specialist**: 8007
- **Memory Service**: 8010
- **Agents Specialist**: 8015

### Health Monitoring

Check service health:
```bash
# Individual service health
curl http://localhost:8000/health

# Comprehensive health check
curl http://localhost:8000/health/services
```

## 📚 API Documentation

Once services are running, access the interactive API documentation:

- **API Gateway**: http://localhost:8000/docs
- **Orchestrator**: http://localhost:8002/docs
- **Memory Service**: http://localhost:8010/docs
- **Checkpoint**: http://localhost:8003/docs



### Memory Storage
```python
# Store conversation context
response = requests.post("http://localhost:8010/memory/store", json={
    "conversation_id": "conv_123",
    "content": "Patient reported headache symptoms",
    "metadata": {"type": "symptom", "severity": "moderate"}
})
```

## 🧪 Development

### Running Tests
```bash
# Run all tests
python -m pytest

# Run specific service tests
python -m pytest tests/test_orchestrator.py
```

### Code Style
```bash
# Format code
black .

# Lint code
flake8 .
```

### Debugging
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python run_dev.py --dev
```

## 🔒 Security Features

- **JWT Authentication**: Secure API access
- **CSRF Protection**: Cross-site request forgery prevention
- **CORS Configuration**: Cross-origin request handling
- **Input Validation**: Pydantic model validation
- **Rate Limiting**: API rate limiting (configurable)
- **Health Monitoring**: Service health checks



### Production Considerations
- Use environment-specific configuration
- Set up database replication and backups
- Use HTTPS in production

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the [API Documentation](http://localhost:8000/docs)
- Review the health endpoints for service status
- Check logs for detailed error information

## 🔄 Version History

- **v1.0.0**: Initial release with core microservices
- Real-time communication support
- Multi-agent specialist system
- Comprehensive memory management