# Orchestrator Architecture Documentation

## Overview

The Orchestrator is the central coordination service in the Polaris conversational AI platform. It acts as the brain of the system, managing conversation flows, coordinating agent interactions, handling checkpoint progression, and orchestrating complex multi-service conversations. Built with FastAPI and designed for high-performance async operations, the orchestrator ensures seamless communication between all platform components.

## System Architecture

```mermaid
graph TB
    subgraph "Orchestrator Core System"
        API[FastAPI Orchestrator] --> ORQ[OrchestrationQuery Handler]
        ORQ --> SCO[SimplifiedOrchestrator]
        
        subgraph "Core Components"
            SCO --> CPM[Checkpoint Manager]
            SCO --> ASM[Agent Service Manager]
            SCO --> CSM[Context State Manager]
            SCO --> TIM[Timing & Metrics]
        end
        
        subgraph "State Management Layer"
            CSM --> SM[State Manager]
            SM --> LCM[Local Cache Manager]
            SM --> RCM[Redis Cache Manager]
            SM --> MSC[Memory Service Client]
        end
        
        subgraph "Service Communication Layer"
            ASM --> SVC[Service Client]
            SVC --> HTTP[HTTP Client Pool]
            SVC --> RET[Retry Logic]
            SVC --> ERR[Error Handling]
        end
    end
    
    subgraph "External Services"
        CHK[Checkpoint Service] --> ORQ
        PRI[Primary Service] --> ORQ
        MEM[Memory Service] --> SM
        
        subgraph "Agent Services"
            CHKL[Checklist Agent]
            PRIV[Privacy Agent]
            NUT[Nutrition Agent]
            FOL[Followup Agent]
            HIS[History Agent]
            HUM[Human Intervention]
            MED[Medication Agent]
        end
        
        subgraph "Specialized Agents"
            LON[Loneliness Companion]
            ACC[Accountability Agent]
            THER[Therapy Agent]
        end
    end
    
    ASM --> CHKL
    ASM --> PRIV
    ASM --> NUT
    ASM --> FOL
    ASM --> HIS
    ASM --> HUM
    ASM --> MED
    ASM --> LON
    ASM --> ACC
    ASM --> THER
```

## Core Components

### 1. SimplifiedOrchestrator

The main orchestration engine that handles conversation flow and service coordination.

**Key Responsibilities:**
- **Conversation Flow Management**: Controls checkpoint progression and task management
- **Service Coordination**: Orchestrates calls to multiple agent services
- **Context Management**: Maintains conversation context and state
- **Performance Optimization**: Implements caching and efficient resource management

```mermaid
sequenceDiagram
    participant Client
    participant Orchestrator
    participant CheckpointService
    participant StateManager
    participant AgentServices
    participant PrimaryService

    Client->>Orchestrator: OrchestrationQuery
    Orchestrator->>StateManager: Get/Create ConversationState
    StateManager-->>Orchestrator: ConversationState
    
    alt New Conversation
        Orchestrator->>CheckpointService: Generate Initial Checkpoints
        CheckpointService-->>Orchestrator: Checkpoint List
        Orchestrator->>StateManager: Set Tasks & Checkpoints
    end
    
    Orchestrator->>StateManager: Get Current Checkpoint
    StateManager-->>Orchestrator: Current Checkpoint
    
    opt Checkpoint Evaluation
        Orchestrator->>AgentServices: Evaluate Checkpoint Progress
        AgentServices-->>Orchestrator: Evaluation Result
    end
    
    Orchestrator->>PrimaryService: Process with Context
    PrimaryService-->>Orchestrator: Primary Response
    
    Orchestrator->>StateManager: Update State (Background)
    Orchestrator-->>Client: OrchestratorResponse
```

### 2. State Management System

Ultra-optimized conversation state management with multi-level caching.

**Features:**
- **Multi-Level Caching**: Local memory + Redis + API fallback
- **Incremental Updates**: Only save changed fields
- **Async Operations**: Non-blocking state updates
- **Performance Monitoring**: Detailed cache statistics

```mermaid
stateDiagram-v2
    [*] --> StateInitialization: Get/Create State
    StateInitialization --> CacheCheck: Check Local Cache
    CacheCheck --> LocalHit: Cache Hit
    CacheCheck --> RedisCheck: Cache Miss
    RedisCheck --> RedisHit: Redis Hit
    RedisCheck --> APIFallback: Redis Miss
    APIFallback --> StateLoaded: API Response
    LocalHit --> StateLoaded
    RedisHit --> StateLoaded
    
    StateLoaded --> ConversationFlow: Process Request
    ConversationFlow --> StateUpdate: Update Fields
    StateUpdate --> DirtyTracking: Mark Dirty Fields
    DirtyTracking --> AsyncSave: Background Save
    AsyncSave --> [*]
```

### 3. Service Communication Layer

Robust HTTP client management with advanced error handling and retry logic.

**Capabilities:**
- **Connection Pooling**: Optimized HTTP/2 connections
- **Dynamic Timeouts**: Service-specific timeout configurations
- **Intelligent Retries**: Exponential backoff with circuit breaker patterns
- **Error Classification**: Different handling for different error types

```mermaid
flowchart TD
    A[Service Call Request] --> B{HTTP Client Ready?}
    B -->|No| C[Initialize HTTP Client]
    B -->|Yes| D[Select Service Timeout]
    C --> D
    
    D --> E[Attempt Service Call]
    E --> F{Response Status}
    
    F -->|Success 2xx| G[Parse JSON Response]
    F -->|Client Error 4xx| H[No Retry - Return Error]
    F -->|Server Error 5xx| I{Retry Attempts Left?}
    F -->|Timeout| J{Retry Attempts Left?}
    F -->|Connection Error| K{Retry Attempts Left?}
    
    I -->|Yes| L[Exponential Backoff]
    I -->|No| M[Return Service Error]
    J -->|Yes| L
    J -->|No| N[Return Timeout Error]
    K -->|Yes| O[Short Backoff]
    K -->|No| P[Return Connection Error]
    
    L --> E
    O --> E
    G --> Q[Return Success]
    
    H --> R[HTTP Exception]
    M --> S[Service Exception]
    N --> T[Timeout Exception]
    P --> U[Connection Exception]
```

## Service Integration Architecture

### Agent Service Configuration

```python
AGENT_CONFIG = {
    "primary": {"port": 8004, "path": "/process", "type": "core", "dependencies": []},
    "checklist": {"port": 8007, "path": "/process", "type": "sync", "dependencies": []},
    "privacy": {"port": 8011, "path": "/process", "type": "sync", "dependencies": []},
    "nutrition": {"port": 8005, "path": "/process", "type": "sync", "dependencies": ["privacy", "followup"]},
    "followup": {"port": 8008, "path": "/process", "type": "sync", "dependencies": []},
    "history": {"port": 8009, "path": "/process", "type": "async", "dependencies": []},
    "human_intervention": {"port": 8006, "path": "/process", "type": "sync", "dependencies": []},
    "medication": {"port": 8012, "path": "/process", "type": "sync", "dependencies": []},
}
```

### Service Dependencies and Execution Flow

```mermaid
graph TD
    subgraph "Service Dependency Resolution"
        A[Agent Request] --> B[Resolve Dependencies]
        B --> C[Privacy Agent]
        B --> D[Followup Agent]
        C --> E[Nutrition Agent]
        D --> E
        E --> F[Execute All Agents]
        
        G[Independent Agents]
        G --> H[Checklist Agent]
        G --> I[History Agent]
        G --> J[Medication Agent]
        G --> K[Human Intervention]
    end
    
    subgraph "Execution Types"
        L[Sync Agents] --> M[Sequential Execution]
        N[Async Agents] --> O[Parallel Execution]
        P[Core Agents] --> Q[Always Execute]
    end
```

## Conversation Flow Management

### Checkpoint Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Generated: Checkpoint Created
    Generated --> Pending: Added to Task
    Pending --> InProgress: User Interaction
    InProgress --> Evaluating: Check Completion
    Evaluating --> Complete: Criteria Met
    Evaluating --> InProgress: Criteria Not Met
    Complete --> NextCheckpoint: Advance Flow
    NextCheckpoint --> [*]: Task Complete
    
    InProgress --> Paused: Conversation Paused
    Paused --> InProgress: Conversation Resumed
```

### Task Stack Management

The orchestrator manages multiple tasks simultaneously using a stack-based approach:

```mermaid
graph TB
    subgraph "Task Stack Structure"
        TS[Task Stack] --> MT[Main Task]
        TS --> ST1[Support Task 1]
        TS --> ST2[Support Task 2]
        TS --> ST3[Support Task 3]
        
        MT --> MC[Main Checkpoints]
        ST1 --> SC1[Privacy Checklist]
        ST2 --> SC2[Nutrition Checklist]
        ST3 --> SC3[Followup Checklist]
    end
    
    subgraph "Task Execution Flow"
        A[Current Task] --> B{Task Active?}
        B -->|Yes| C[Execute Current Checkpoint]
        B -->|No| D[Find Next Active Task]
        C --> E{Checkpoint Complete?}
        E -->|Yes| F[Advance to Next Checkpoint]
        E -->|No| G[Continue Current Checkpoint]
        F --> H{More Checkpoints?}
        H -->|Yes| I[Next Checkpoint]
        H -->|No| J[Mark Task Complete]
        D --> C
        I --> C
        J --> D
    end
```

## Performance Optimizations

### Caching Strategy

```mermaid
graph LR
    subgraph "Multi-Level Cache Architecture"
        A[Request] --> B[Local Memory Cache]
        B -->|Hit| C[Return Cached Data]
        B -->|Miss| D[Redis Cache]
        D -->|Hit| E[Cache Locally & Return]
        D -->|Miss| F[API Call]
        F --> G[Cache in All Levels]
        G --> H[Return Data]
    end
    
    subgraph "Cache Policies"
        I[Conversation State: 1 hour TTL]
        J[Checkpoint Evaluation: 1 minute TTL]
        K[Task State: 5 minutes TTL]
        L[Context: 5 minutes TTL]
    end
```

### HTTP Client Optimization

```python
# Optimized HTTP client configuration
limits = httpx.Limits(
    max_keepalive_connections=50,
    max_connections=200,
    keepalive_expiry=30.0
)

timeout = httpx.Timeout(
    connect=5.0,
    read=30.0,
    write=15.0,
    pool=10.0
)

http_client = httpx.AsyncClient(
    timeout=timeout,
    limits=limits,
    http2=True,  # Enable HTTP/2 for connection multiplexing
    transport=httpx.AsyncHTTPTransport(
        http2=True,
        retries=2
    )
)
```

## Error Handling and Resilience

### Circuit Breaker Pattern

```mermaid
stateDiagram-v2
    [*] --> Closed: Normal Operation
    Closed --> Open: Failure Threshold Reached
    Open --> HalfOpen: Timeout Elapsed
    HalfOpen --> Closed: Success
    HalfOpen --> Open: Failure
    
    Closed: Accept Requests
    Open: Reject Requests
    HalfOpen: Test Single Request
```

### Retry Logic Implementation

```python
async def call_service_with_retry(url, payload, max_retries=3):
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # Exponential backoff
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
            
            response = await http_client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code in [400, 401, 403, 404, 422]:
                break  # Don't retry client errors
        except httpx.TimeoutException:
            if attempt == max_retries:
                raise HTTPException(504, "Service timeout")
        except httpx.RequestError:
            if attempt > 0:
                break  # Don't retry connection errors beyond first attempt
    
    raise HTTPException(502, f"Service failed after {max_retries + 1} attempts")
```

## Monitoring and Observability

### Timing Metrics

The orchestrator provides detailed performance metrics for all operations:

```python
class TimingMetrics:
    def __init__(self):
        self.metrics = defaultdict(float)
        self.start_times = {}

    def start(self, step_name: str):
        self.start_times[step_name] = time.time()

    def end(self, step_name: str):
        if step_name in self.start_times:
            duration = time.time() - self.start_times[step_name]
            self.metrics[step_name] = round(duration * 1000, 2)  # milliseconds
```

### Performance Monitoring

```mermaid
graph TB
    subgraph "Metrics Collection"
        A[Request Start] --> B[Timing Metrics]
        B --> C[State Initialization]
        B --> D[Checkpoint Preparation]
        B --> E[Service Calls]
        B --> F[Response Generation]
        
        C --> G[Total Time: State]
        D --> H[Total Time: Checkpoints]
        E --> I[Total Time: Services]
        F --> J[Total Time: Response]
    end
    
    subgraph "Metrics Output"
        K[HTTP Headers] --> L[Server-Timing]
        M[Response Body] --> N[Timing Metrics]
        O[Logs] --> P[Performance Data]
    end
```

## Configuration Management

### Environment Configuration

```python
class OrchestratorSettings(BaseSettings):
    # Core Service URLs
    MEMORY_URL: str = "http://localhost:8010"
    CHECKPOINT_URL: str = "http://localhost:8003"
    PRIMARY_SERVICE_URL: str = "http://localhost:8004/process"
    
    # Agent Service URLs
    CHECKLIST_SERVICE_URL: str = "http://localhost:8007/process"
    PRIVACY_SERVICE_URL: str = "http://localhost:8011/process"
    NUTRITION_SERVICE_URL: str = "http://localhost:8005/process"
    
    # Performance Configuration
    HTTP_CONNECT_TIMEOUT: float = 5.0
    HTTP_READ_TIMEOUT: float = 30.0
    MAX_KEEPALIVE_CONNECTIONS: int = 50
    MAX_CONNECTIONS: int = 200
    
    # Cache Configuration
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL: int = 3600
    LOCAL_CACHE_SIZE: int = 1000
```

### Service-Specific Timeouts

```python
SERVICE_TIMEOUTS = {
    "default": httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=10.0),
    "human_intervention": httpx.Timeout(connect=3.0, read=10.0, write=10.0, pool=5.0),
    "checklist": httpx.Timeout(connect=3.0, read=15.0, write=10.0, pool=5.0),
    "primary_enriched": httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=15.0),
    "medication": httpx.Timeout(connect=5.0, read=45.0, write=20.0, pool=10.0),
    "privacy": httpx.Timeout(connect=5.0, read=45.0, write=20.0, pool=10.0),
}
```

## API Endpoints

### Main Orchestration Endpoint

```http
POST /orchestrate
```

**Request Model:**
```python
class OrchestratorQuery(BaseModel):
    text: str
    conversation_id: str
    plan: str
    services: List[str]
    individual_id: str
    user_profile_id: str
    detected_agent: str
    agent_instance_id: str
    call_log_id: str
    channel: Optional[str] = None
```

**Response Model:**
```python
class OrchestratorResponse(BaseModel):
    response: str
    conversation_id: str
    checkpoints: List[str]
    checkpoint_progress: Dict[str, bool]
    task_stack: List[Dict[str, Any]]
    sync_agent_results: Dict[str, List[AgentResult]]
    async_agent_results: Dict[str, Dict[str, Any]]
    requires_human: bool
    is_paused: bool
    is_enriched: bool
    timing_metrics: Dict[str, float]
```

### Health Check Endpoint

```http
GET /health
```

**Response:**
```json
{
    "status": "healthy",
    "service": "orchestrator",
    "version": "simplified"
}
```

## Integration Patterns

### Agent Detection and Routing

```mermaid
flowchart TD
    A[User Query] --> B[Agent Detection]
    B --> C{Detected Agent Type}
    
    C -->|loneliness| D[Loneliness Companion Service]
    C -->|accountability| E[Accountability Agent Service]
    C -->|general| F[Primary Service with Agents]
    
    D --> G[Loneliness Response]
    E --> H[Accountability Response]
    F --> I[Primary Response + Agent Results]
    
    G --> J[Update Conversation State]
    H --> J
    I --> J
    
    J --> K[Return Orchestrated Response]
```

### Background Task Processing

```python
# Background tasks for non-blocking operations
background_tasks.add_task(
    _handle_simple_background_operations,
    state, query, primary_result
)

background_tasks.add_task(
    _generate_next_checkpoint,
    query.conversation_id,
    query.text,
    context,
    task.get('task_id'),
    state,
    query.detected_agent
)
```

## Best Practices

### Service Call Optimization

1. **Connection Reuse**: Use persistent HTTP connections
2. **Timeout Management**: Set appropriate timeouts per service
3. **Retry Logic**: Implement intelligent retry with backoff
4. **Error Handling**: Classify errors for appropriate responses

### State Management Best Practices

1. **Incremental Updates**: Only save changed fields
2. **Async Operations**: Non-blocking state persistence
3. **Cache Layering**: Multi-level cache with intelligent fallback
4. **Dirty Tracking**: Track changes for efficient updates

### Performance Guidelines

1. **Resource Pooling**: Reuse HTTP clients and connections
2. **Caching Strategy**: Cache frequently accessed data
3. **Background Processing**: Offload non-critical operations
4. **Metrics Monitoring**: Track performance continuously

## Troubleshooting

### Common Issues

1. **Service Timeouts**: Check service health and timeout configurations
2. **Memory Leaks**: Monitor cache sizes and cleanup policies
3. **Connection Exhaustion**: Review connection pool settings
4. **State Synchronization**: Verify Redis connectivity and fallback mechanisms

### Debug Commands

```python
# Check service health
await check_service_health("primary")

# Get cache statistics
cache_stats = cache_manager.get_stats()

# Monitor HTTP client status
print(f"Active connections: {http_client._pool._pool_for_request}")
```

## Future Enhancements

### Planned Features

1. **GraphQL Integration**: Alternative query interface
2. **Event Streaming**: Real-time state updates
3. **Service Mesh**: Advanced service discovery and routing
4. **ML-Based Routing**: Intelligent agent selection
5. **Distributed Tracing**: End-to-end request tracking

### Scalability Improvements

1. **Horizontal Scaling**: Multiple orchestrator instances
2. **Load Balancing**: Request distribution strategies
3. **Cache Distribution**: Distributed Redis clusters
4. **Service Partitioning**: Domain-specific orchestrators