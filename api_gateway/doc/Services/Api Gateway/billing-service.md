# Billing Service Documentation

## Overview

The Billing Service is a comprehensive plan and subscription management system for the healthcare platform. It handles plan selection, service configuration, and billing operations for both hospitals and individual healthcare providers.

## Table of Contents

1. [Architecture](#architecture)
2. [Plan Types](#plan-types)
3. [API Endpoints](#api-endpoints)
4. [Data Models](#data-models)
5. [Service Flow](#service-flow)
6. [Authentication & Authorization](#authentication--authorization)
7. [Error Handling](#error-handling)
8. [Testing](#testing)
9. [Configuration](#configuration)

## Architecture

The billing service follows a modular architecture:

```
billing/
├── main.py          # Module exports and initialization
├── routes.py        # FastAPI route definitions
├── controller.py    # Business logic and database operations
├── schema.py        # Pydantic models and validation
└── config.json      # Plan configuration data
```

### Key Components

- **Router**: FastAPI router handling HTTP requests
- **Controller**: Business logic layer with database operations
- **Schema**: Pydantic models for request/response validation
- **Authentication**: JWT-based authentication middleware

## Plan Types

The system supports role-based plan types:

### Hospital Plans
- **LITE Plan**: Basic features for small healthcare organizations
  - Max Agents: 5
  - Services: Privacy, Human Escalation, Checklist, Medication, Nutrition
  - Model Tier: Basic
  - Rate Limit: 60 requests/minute
  - Price: $499/month ($4,790.40/year)

- **PRO Plan**: Advanced features for growing organizations
  - Max Agents: 50
  - Services: All available services
  - Model Tier: Premium
  - Rate Limit: 300 requests/minute
  - Price: $999/month ($9,590.40/year)

### Individual Plans
- **LITE Plan**: Standard features for individual practitioners
  - Max Agents: 1
  - Services: Basic service
  - Model Tier: Basic
  - Rate Limit: 30 requests/minute
  - Price: $49/month ($470.40/year)

- **PRO Plan**: Extra capacity for busy practitioners
  - Max Agents: 2
  - Services: Basic service
  - Model Tier: Advanced
  - Rate Limit: 120 requests/minute
  - Price: $99/month ($950.40/year)

## API Endpoints

### 1. Get Available Plans

**Endpoint**: `GET /billing/plan`

**Description**: Returns available plans based on user role

**Authentication**: Required (JWT)

**Response**:
```json
{
  "plans": [
    {
      "plan_type": "lite",
      "name": "Lite Plan (Hospital)",
      "description": "Essential features for small healthcare organizations",
      "price_monthly": 499.0,
      "price_yearly": 4790.40,
      "max_agents": 5,
      "features": ["Basic patient management", "Standard memory stack"],
      "model_tier": "gemini-1.5",
      "is_recommended": false
    }
  ],
  "user_role": "hospital",
  "current_plan": "lite",
  "current_plan_details": {...}
}
```

### 2. Get Available Services

**Endpoint**: `GET /billing/services`

**Description**: Returns available services based on current plan

**Authentication**: Required (JWT)

**Response**:
```json
{
  "services": [
    {
      "id": "privacy",
      "name": "Privacy Protection",
      "description": "Ensures sensitive patient data is properly anonymized",
      "is_default": true,
      "is_selected": true,
      "is_available": true
    }
  ]
}
```

### 3. Select Services

**Endpoint**: `POST /billing/services/select`

**Description**: Select services for a hospital's plan

**Authentication**: Required (JWT + CSRF Token)

**Headers**:
```
X-CSRF-Token: <csrf_token>
```

**Request Body**:
```json
{
  "hospital_id": "hospital_123",
  "services": ["privacy", "medication", "checklist"]
}
```

**Response**:
```json
{
  "id": "plan_123",
  "hospital_id": "hospital_123",
  "plan_type": "lite",
  "status": "active",
  "max_agents": 5,
  "selected_services": ["privacy", "medication", "checklist"],
  "created_at": "2025-09-15T10:00:00Z",
  "updated_at": "2025-09-15T10:00:00Z"
}
```

### 4. Get Current Plan

**Endpoint**: `GET /billing/plan/current`

**Description**: Get current subscription details for the authenticated user

**Authentication**: Required (JWT)

**Query Parameters** (Admin only):
- `entity_id`: Hospital or Individual ID

**Response** (Hospital):
```json
{
  "id": "plan_123",
  "hospital_id": "hospital_123",
  "plan_type": "pro",
  "status": "active",
  "max_agents": 50,
  "available_services": ["privacy", "human_escalation"],
  "selected_services": ["privacy", "medication"],
  "model_tier": "premium",
  "created_at": "2025-09-15T10:00:00Z"
}
```

### 5. Select Plan

**Endpoint**: `POST /billing/plan/select`

**Description**: Select a plan for hospital or individual

**Authentication**: Required (JWT + CSRF Token)

**Headers**:
```
X-CSRF-Token: <csrf_token>
```

**Request Body**:
```json
{
  "plan_type": "pro",
  "id": "hospital_123"
}
```

**Success Response**: `200 OK`

## Data Models

### Core Enums

```python
class PlanType(str, Enum):
    LITE = "lite"
    PRO = "pro"
    HOBBY = "hobby"
    BASIC = "basic"

class ServiceType(str, Enum):
    CHECKPOINT = "checkpoint"
    PRIMARY = "primary"
    CHECKLIST = "checklist"
    MEDICATION = "medication"
    NUTRITION = "nutrition"
    PRIVACY = "privacy"
    SUMMARY = "summary"
    HUMAN_ESCALATION = "human_escalation"

class PlanStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class UserRole(str, Enum):
    ADMIN = "admin"
    HOSPITAL = "hospital"
    ASSISTANT = "assistant"
    INDIVIDUAL = "individual"
```

### Request Models

#### PlanSelectionRequest
```python
{
  "plan_type": "lite",  # Required: Plan type to select
  "id": "hospital_123"  # Required: Hospital or individual ID
}
```

#### ServiceSelectionRequest
```python
{
  "hospital_id": "hospital_123",  # Required: Hospital ID
  "services": ["privacy", "medication"]  # Required: List of services
}
```

### Response Models

#### HospitalPlanResponse
Contains complete hospital plan details including configuration and limits.

#### IndividualPlanResponse
Contains complete individual plan details with plan-specific configurations.

## Service Flow

### Plan Selection Flow

1. **Authentication**: User authenticates via JWT
2. **Role Validation**: System validates user role and permissions
3. **Plan Validation**: System validates selected plan type for user role
4. **Database Update**: Plan is created or updated in database
5. **Response**: Updated plan details returned to client

### Service Selection Flow

1. **Authentication**: User authenticates with JWT + CSRF token
2. **Permission Check**: Verify user can modify the specified hospital
3. **Plan Validation**: Ensure hospital has an active plan
4. **Service Validation**: Validate services against plan limits
5. **Database Update**: Services updated in hospital plan
6. **Response**: Updated plan with selected services

### Plan Restrictions

#### LITE Plan Restrictions
- Maximum 1 optional service (medication OR nutrition)
- Default services always included: privacy, human_escalation, checklist

#### PRO Plan Restrictions
- All services available
- No service selection limits

## Authentication & Authorization

### JWT Authentication
All endpoints require valid JWT token in Authorization header:
```
Authorization: Bearer <jwt_token>
```

### CSRF Protection
Write operations require CSRF token:
```
X-CSRF-Token: <csrf_token>
```

### Role-Based Access Control

| Role | Permissions |
|------|------------|
| **ADMIN** | Full access to all plans and services |
| **HOSPITAL** | Manage own hospital's plan and services |
| **INDIVIDUAL** | Manage own individual plan |
| **ASSISTANT** | View services from associated hospital |

### Permission Matrix

| Endpoint | Admin | Hospital | Individual | Assistant |
|----------|-------|----------|------------|-----------|
| GET /plan | ✅ | ✅ | ✅ | ❌ |
| GET /services | ✅ | ✅ | ✅ | ✅ |
| POST /services/select | ✅ | ✅ (own) | ❌ | ❌ |
| GET /plan/current | ✅ | ✅ (own) | ✅ (own) | ❌ |
| POST /plan/select | ✅ | ✅ (own) | ✅ (own) | ❌ |

## Error Handling

### Common Error Responses

#### 400 Bad Request
```json
{
  "detail": "Invalid plan type"
}
```

#### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

#### 403 Forbidden
```json
{
  "detail": "Only hospital administrators can select services"
}
```

#### 404 Not Found
```json
{
  "detail": "Hospital plan not found"
}
```

#### 500 Internal Server Error
```json
{
  "detail": "Error retrieving available plans: Database connection failed"
}
```

### Error Scenarios

1. **Plan Not Found**: When user tries to access non-existent plan
2. **Invalid Permissions**: When user tries to access unauthorized resources
3. **Plan Status Issues**: When trying to modify inactive/cancelled plans
4. **Service Limits**: When selecting too many services for LITE plan
5. **Database Errors**: When database operations fail

## Testing

### Unit Tests

Test the controller methods:

```python
import pytest
from billing.controller import BillingController

@pytest.fixture
def billing_controller():
    return BillingController()

async def test_get_available_plans_hospital(billing_controller):
    """Test available plans for hospital role"""
    result = await billing_controller.get_available_plans(
        user_role=UserRole.HOSPITAL,
        role_entity_id="hospital_123"
    )
    assert len(result.plans) == 2
    assert result.user_role == UserRole.HOSPITAL

async def test_select_services_lite_plan_limit(billing_controller):
    """Test service selection limits for LITE plan"""
    request = ServiceSelectionRequest(
        hospital_id="hospital_123",
        services=["medication", "nutrition"]  # Should fail for LITE
    )
    
    with pytest.raises(HTTPException) as exc:
        await billing_controller.select_services(request, "user_123")
    
    assert exc.value.status_code == 400
    assert "one optional service" in exc.value.detail
```

### Integration Tests

Test the API endpoints:

```python
import pytest
from fastapi.testclient import TestClient
from api_gateway.main import app

client = TestClient(app)

def test_get_available_plans():
    """Test GET /billing/plan endpoint"""
    headers = {"Authorization": "Bearer valid_jwt_token"}
    response = client.get("/billing/plan", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert "user_role" in data

def test_select_services_with_csrf():
    """Test POST /billing/services/select with CSRF"""
    headers = {
        "Authorization": "Bearer valid_jwt_token",
        "X-CSRF-Token": "valid_csrf_token"
    }
    payload = {
        "hospital_id": "hospital_123",
        "services": ["privacy", "medication"]
    }
    
    response = client.post("/billing/services/select", 
                          json=payload, headers=headers)
    
    assert response.status_code == 200
```

### Test Data Setup

```python
# Test data for plans
TEST_HOSPITAL_PLAN = {
    "id": "plan_test_123",
    "hospital_id": "hospital_test_123",
    "plan_type": "lite",
    "status": "active",
    "max_agents": 5,
    "selected_services": ["privacy", "checklist"],
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow()
}

# Test data for hospitals
TEST_HOSPITAL = {
    "id": "hospital_test_123",
    "name": "Test Hospital",
    "plan": "lite"
}
```

### Load Testing

Test plan selection performance:

```python
import asyncio
import aiohttp

async def load_test_plan_selection():
    """Load test plan selection endpoint"""
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(100):
            task = session.get(
                "http://localhost:8000/billing/plan",
                headers={"Authorization": f"Bearer token_{i}"}
            )
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        success_count = sum(1 for r in responses if r.status == 200)
        print(f"Success rate: {success_count}/100")
```

## Configuration

### Environment Variables

```bash
# Database configuration
MONGODB_URL=mongodb://localhost:27017/healthcare_db

# JWT configuration
JWT_SECRET_KEY=your_secret_key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# CSRF configuration
CSRF_SECRET_KEY=your_csrf_secret
```

### Plan Configuration

Plan limits are defined in `config.json`:

```json
{
  "lite": {
    "max_agents": 5,
    "available_services": ["privacy", "checklist", "medication"],
    "model_tier": "gemini-flash",
    "rate_limit_per_minute": 100
  },
  "pro": {
    "max_agents": 15,
    "available_services": ["privacy", "checklist", "medication", "nutrition"],
    "model_tier": "gemini-pro",
    "rate_limit_per_minute": 500
  }
}
```

### Database Collections

The service uses these MongoDB collections:

- **plans**: Stores hospital and individual plans
- **hospitals**: Hospital information and plan references
- **individuals**: Individual user information
- **assistants**: Assistant user information
- **plan_update_history**: Plan change history

### Database Indexes

Optimized indexes for performance:

```javascript
// Plans collection
db.plans.createIndex({"hospital_id": 1})
db.plans.createIndex({"individual_id": 1}, {unique: true})
db.plans.createIndex({"plan_type": 1})
db.plans.createIndex({"status": 1})

// Plan history collection
db.plan_update_history.createIndex({"hospital_id": 1})
```

## Security Considerations

1. **Authentication**: All endpoints require valid JWT tokens
2. **Authorization**: Role-based access control prevents unauthorized operations
3. **CSRF Protection**: Write operations require CSRF tokens
4. **Input Validation**: Pydantic models validate all request data
5. **SQL Injection Prevention**: MongoDB queries use parameterized operations
6. **Rate Limiting**: Plan-based rate limiting prevents abuse

## Monitoring and Logging

### Key Metrics to Monitor

- Plan selection success rate
- Service selection response time
- Database query performance
- Authentication failure rate
- CSRF token validation rate

### Logging Points

- Plan selections and updates
- Service configuration changes
- Authentication failures
- Database operation errors
- Rate limit violations

### Health Checks

```python
@router.get("/health")
async def health_check():
    """Health check endpoint for billing service"""
    try:
        # Check database connection
        db = get_database()
        db.plans.find_one({"id": "health_check"})
        
        return {"status": "healthy", "timestamp": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Service unavailable")
```

## Stripe Payment Integration

### Overview

The billing service integrates with Stripe for payment processing, subscription management, and customer billing. This integration handles:

- Secure checkout sessions for plan purchases
- Subscription lifecycle management
- Webhook processing for payment events
- Customer portal for self-service billing
- Payment failure handling and recovery

### Stripe Endpoints

#### 1. Create Checkout Session

**Endpoint**: `POST /stripe/checkout`

**Description**: Creates a Stripe checkout session for plan purchase

**Authentication**: Required (JWT)

**Request Body**:
```json
{
  "plan_type": "lite",
  "billing_cycle": "monthly"
}
```

**Response**:
```json
{
  "checkout_url": "https://checkout.stripe.com/pay/cs_test_..."
}
```

#### 2. Customer Portal

**Endpoint**: `POST /stripe/portal-link`

**Description**: Creates a billing portal session for customer self-service

**Authentication**: Required (JWT)

**Response**:
```json
{
  "portal_url": "https://billing.stripe.com/p/session/test_..."
}
```

#### 3. Get Subscription

**Endpoint**: `GET /stripe/subscription/{sub_id}`

**Description**: Retrieves subscription details

**Authentication**: Required (JWT)

**Response**:
```json
{
  "id": "sub_1234567890",
  "status": "active",
  "current_period_start": 1694764800,
  "current_period_end": 1697443200,
  "metadata": {
    "role": "hospital",
    "role_entity_id": "hospital_123"
  }
}
```

#### 4. Cancel Subscription

**Endpoint**: `POST /stripe/subscription/cancel`

**Description**: Cancels subscription at period end

**Authentication**: Required (JWT)

**Request Body**:
```json
{
  "subscription_id": "sub_1234567890"
}
```

**Response**:
```json
{
  "status": "active"
}
```

#### 5. List Customer Invoices

**Endpoint**: `GET /stripe/customer/{customer_id}/invoices`

**Description**: Lists customer invoices

**Authentication**: Required (JWT)

**Response**:
```json
{
  "data": [
    {
      "id": "in_1234567890",
      "amount_paid": 49900,
      "currency": "usd",
      "status": "paid",
      "created": 1694764800
    }
  ]
}
```

### Admin Endpoints

#### 1. List All Customers

**Endpoint**: `GET /stripe/admin/customers`

**Description**: Lists all Stripe customers (Admin only)

**Authentication**: Required (JWT + Admin role)

#### 2. List All Subscriptions

**Endpoint**: `GET /stripe/admin/subscriptions`

**Description**: Lists all subscriptions (Admin only)

**Authentication**: Required (JWT + Admin role)

### Stripe Configuration

#### Price Mapping

The system maps plan types and billing cycles to Stripe price IDs:

```python
PRICE_MAP = {
    # Hospital prices
    ("hospital", "lite", "monthly"): "price_1RmuCEFVBY798uGmgenKTEZ9",
    ("hospital", "lite", "yearly"): "price_1RmuGuFVBY798uGmLdZIB5ht",
    ("hospital", "pro", "monthly"): "price_1RmuccFVBY798uGmmr4xqM4E",
    ("hospital", "pro", "yearly"): "price_1RmueIFVBY798uGmbKqqnA6N",
    
    # Individual prices  
    ("individual", "lite", "monthly"): "price_1RmugNFVBY798uGmI9U07uyf",
    ("individual", "lite", "yearly"): "price_1RmuhKFVBY798uGmwNxbILhR",
    ("individual", "pro", "monthly"): "price_1RmuibFVBY798uGmVqAyfsfs",
    ("individual", "pro", "yearly"): "price_1RmujKFVBY798uGmZUHIQiPO"
}
```

#### Environment Variables

```bash
# Stripe API Keys
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_API_VERSION=2023-10-16

# Price IDs for Hospital Plans
PRICE_HOSP_LITE_MONTHLY=price_1RmuCEFVBY798uGmgenKTEZ9
PRICE_HOSP_LITE_YEARLY=price_1RmuGuFVBY798uGmLdZIB5ht
PRICE_HOSP_PRO_MONTHLY=price_1RmuccFVBY798uGmmr4xqM4E
PRICE_HOSP_PRO_YEARLY=price_1RmueIFVBY798uGmbKqqnA6N

# Price IDs for Individual Plans
PRICE_IND_LITE_MONTHLY=price_1RmugNFVBY798uGmI9U07uyf
PRICE_IND_LITE_YEARLY=price_1RmuhKFVBY798uGmwNxbILhR
PRICE_IND_PRO_MONTHLY=price_1RmuibFVBY798uGmVqAyfsfs
PRICE_IND_PRO_YEARLY=price_1RmujKFVBY798uGmZUHIQiPO

# Redirect URLs
STRIPE_SUCCESS_URL=http://localhost:3000/stripe/success
STRIPE_CANCEL_URL=http://localhost:3000/stripe/cancel
```

### Webhook Processing

#### Webhook Endpoint

**Endpoint**: `POST /stripe/webhook`

**Description**: Processes Stripe webhook events

**Authentication**: Stripe signature verification

#### Supported Events

1. **checkout.session.completed**
   - Activates plan after successful payment
   - Creates customer and subscription records
   - Sets default services for new plans

2. **invoice.payment_succeeded**
   - Reactivates suspended plans
   - Records payment details in database
   - Updates plan status to ACTIVE

3. **invoice.payment_failed**
   - Suspends plan due to payment failure
   - Logs failure for follow-up
   - Updates plan status to SUSPENDED

4. **customer.subscription.updated**
   - Handles plan changes and status updates
   - Manages subscription pauses/resumes
   - Updates plan status accordingly

5. **customer.subscription.deleted**
   - Handles subscription cancellations
   - Updates plan status to CANCELLED
   - Preserves historical data

#### Webhook Security

- **Signature Verification**: All webhooks verified using Stripe signature
- **Idempotency**: Duplicate event handling prevented
- **Error Handling**: Failed webhooks logged for retry
- **Audit Trail**: All webhook events logged to `stripe_audit` collection

### Payment Flow

#### Subscription Purchase Flow

1. **User Selection**: User selects plan and billing cycle
2. **Checkout Creation**: System creates Stripe checkout session
3. **Payment Processing**: User completes payment on Stripe
4. **Webhook Receipt**: System receives `checkout.session.completed`
5. **Plan Activation**: Plan activated and services configured
6. **Customer Creation**: Stripe customer ID stored in database

#### Payment Failure Recovery

1. **Payment Failure**: Stripe sends `invoice.payment_failed` webhook
2. **Plan Suspension**: System suspends plan (status: SUSPENDED)
3. **User Notification**: User receives payment failure notification
4. **Retry Payment**: User can retry payment via customer portal
5. **Plan Reactivation**: Successful payment reactivates plan

### Database Integration

#### Plans Collection Updates

Stripe integration adds these fields to plans:

```javascript
{
  // Existing plan fields...
  "stripe_customer_id": "cus_1234567890",
  "stripe_subscription_id": "sub_1234567890",
  "status": "active" // Updated based on payment status
}
```

#### Payments Collection

Comprehensive payment tracking:

```javascript
{
  "stripe_checkout_session_id": "cs_test_...",
  "stripe_customer_id": "cus_...",
  "stripe_subscription_id": "sub_...",
  "stripe_invoice_id": "in_...",
  "stripe_payment_intent_id": "pi_...",
  "stripe_charge_id": "ch_...",
  "role": "hospital",
  "role_entity_id": "hospital_123",
  "plan_type": "lite",
  "cycle": "monthly",
  "amount": 49900,
  "currency": "usd",
  "net_amount": 47155,
  "fee_amount": 2745,
  "payment_method": {
    "type": "card",
    "card": {
      "brand": "visa",
      "last4": "4242",
      "exp_month": 12,
      "exp_year": 2025
    }
  },
  "paid_at": "2025-09-15T10:00:00Z",
  "created_at": "2025-09-15T10:00:00Z"
}
```

#### Audit Collection

Webhook event logging:

```javascript
{
  "event_type": "checkout_completed",
  "payload": {...},
  "status": "ok",
  "note": "",
  "created_at": "2025-09-15T10:00:00Z"
}
```

### Error Handling

#### Stripe-Specific Errors

```python
# Invalid price ID
{
  "detail": "Price mapping not found for (hospital, lite, monthly)"
}

# Subscription not found
{
  "detail": "No such subscription: sub_invalid"
}

# Unauthorized subscription access
{
  "detail": "Unauthorized"
}

# Webhook signature verification failed
{
  "detail": "Invalid webhook signature"
}
```

#### Retry Logic

- **API Calls**: 2 automatic retries for network failures
- **Webhook Processing**: Failed webhooks logged for manual retry
- **Payment Intent**: Automatic retry for temporary failures

### Testing Stripe Integration

#### Test Cards

```javascript
// Successful payment
"4242424242424242"

// Payment failure
"4000000000000002" 

// Requires authentication
"4000000000003220"

// Insufficient funds
"4000000000009995"
```

#### Test Webhooks

```bash
# Install Stripe CLI
stripe listen --forward-to localhost:8000/stripe/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.updated
```

#### Integration Tests

```python
async def test_checkout_creation():
    """Test checkout session creation"""
    payload = {
        "plan_type": "lite",
        "billing_cycle": "monthly"
    }
    response = await client.post("/stripe/checkout", 
                               json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "checkout_url" in data
    assert "checkout.stripe.com" in data["checkout_url"]

async def test_webhook_processing():
    """Test webhook event processing"""
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_status": "paid",
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
                "metadata": {
                    "role": "hospital",
                    "role_entity_id": "hospital_123",
                    "plan": "lite"
                }
            }
        }
    }
    
    response = await client.post("/stripe/webhook", 
                               json=webhook_payload, 
                               headers=webhook_headers)
    
    assert response.status_code == 200
    
    # Verify plan was activated
    plan = db.plans.find_one({"hospital_id": "hospital_123"})
    assert plan["status"] == "active"
    assert plan["stripe_customer_id"] == "cus_test_123"
```

### Security Considerations

1. **API Keys**: Secure storage of Stripe secret keys
2. **Webhook Signatures**: All webhooks cryptographically verified
3. **Customer Data**: PCI compliance through Stripe's secure vault
4. **Access Control**: Users can only access their own subscriptions
5. **Audit Logging**: All payment events logged for compliance

### Monitoring Stripe Integration

#### Key Metrics

- Checkout conversion rate
- Payment success/failure rates
- Webhook processing latency
- Subscription churn rate
- Revenue by plan type

#### Alerts

- Failed webhook processing
- High payment failure rate
- Subscription cancellation spikes
- API error rate increases

#### Health Checks

```python
@router.get("/stripe/health")
async def stripe_health_check():
    """Check Stripe API connectivity"""
    try:
        stripe.Account.retrieve()
        return {"status": "healthy", "service": "stripe"}
    except stripe.error.AuthenticationError:
        raise HTTPException(status_code=503, detail="Stripe authentication failed")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Stripe service unavailable: {str(e)}")
```

## Deployment Notes

1. **Database Migrations**: Ensure indexes are created before deployment
2. **Environment Variables**: Configure all required environment variables
3. **Load Balancing**: Service supports horizontal scaling
4. **Monitoring**: Set up monitoring for key metrics and health checks
5. **Backup**: Regular backup of plans and configuration data
6. **Stripe Configuration**: 
   - Set up webhook endpoints in Stripe dashboard
   - Configure price IDs for all plan combinations
   - Enable automatic tax calculation if required
   - Set up customer portal settings

---

This documentation covers the complete billing service implementation including Stripe payment integration. For additional questions or support, refer to the API Gateway documentation or contact the development team.