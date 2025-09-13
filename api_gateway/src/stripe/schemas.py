from pydantic import BaseModel, Field, HttpUrl
from enum import Enum
from ..billing.schema import PlanType

class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"

class CheckoutBody(BaseModel):
    plan_type: PlanType = Field(..., description="Chosen plan")
    billing_cycle: BillingCycle = Field(..., description="monthly or yearly")

class CheckoutURL(BaseModel):
    checkout_url: HttpUrl 
