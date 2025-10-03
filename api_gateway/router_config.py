# api_gateway/router_config.py
"""
Router configuration for API Gateway
Centralized router management separated from main.py
"""

# async def initialize_schedule_controller():
#     """Initialize the schedule controller - should be called on startup"""
#     try:
#         from .src.schedule.routes import schedule_controller_instance
#         await schedule_controller_instance.ensure_initialized()
#     except Exception as e:
#         import logging
#         logger = logging.getLogger(__name__)
#         logger.error(f"Failed to initialize schedule controller: {e}")

def setup_routers(app):
    """Configure all application routers"""
    
    # Import all routers
    # from .src.phone.routes import phone_router as phone_router
    # from .src.schedule.routes import schedule_router as schedule_router
    # from .src.schedule.routes import tracking_router as tracking_router
    from .src.auth.routes import router as auth_router
    from .src.auth.otp_routes import router as otp_router
    from .src.billing.routes import router as billing_router
    from .src.stripe.routes import router as stripe_router
    from .src.userProfile.routes import router as userprofile_router
    from .src.initial_call_handler.routes import app as initial_call_handler_router
    from .src.livekit.livekit import router as livekit_router
    from .src.metrics.routes import router as metrics_router
    from .src.metrics.agent_routes import router as agent_metrics_router
    from .src.documentation.router import router as documentation_router
    from .src.public.routes import router as public_router

    # Core authentication and user management
    app.include_router(auth_router, tags=["Authentication"])
    app.include_router(otp_router, tags=["OTP"])
    
    # Patient management
    app.include_router(userprofile_router, tags=["User Profiles"])
    
    # Communication services
    # app.include_router(phone_router, tags=["Phone Services"])
    # app.include_router(schedule_router, tags=["Scheduling"])
    # app.include_router(tracking_router, tags=["Tracking"])
    
    # Data and EHR
    
    # Billing and payments
    app.include_router(billing_router, tags=["Billing"])
    app.include_router(stripe_router, tags=["Payments"])
    # Public (no-auth) billing endpoints for funnel
    app.include_router(public_router, tags=["Public Billing"])
    
    # Voice and AI services
    app.include_router(livekit_router, prefix="/api/v1/voice", tags=["Voice Assistant"])
    app.include_router(initial_call_handler_router, tags=["Call Handling"])
    
    # Analytics and monitoring
    app.include_router(metrics_router, tags=["Metrics"])
    app.include_router(agent_metrics_router, tags=["Agent Metrics"])
    
    # Documentation
    app.include_router(documentation_router, tags=["Documentation"])

    return app
