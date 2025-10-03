from pydantic import BaseModel, Field, HttpUrl
from enum import Enum
from ..billing.schema import PlanType

class BillingCycle(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"

class CheckoutBody(BaseModel):
    plan_type: PlanType = Field(..., description="Chosen plan (new Leapply plan types)")
    # Deprecated: kept optional for backward compatibility; ignored by server
    billing_cycle: BillingCycle | None = Field(None, description="Deprecated; ignored")

class CheckoutURL(BaseModel):
    checkout_url: HttpUrl 
