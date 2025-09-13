from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import os

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses"""
    
    async def dispatch(self, request, call_next):
        # Skip preflight requests (OPTIONS) to avoid interfering with CORS
        if request.method == "OPTIONS":
            response = await call_next(request)
            return response
            
        response = await call_next(request)
        
        # Content Security Policy (CSP)
        # Customize based on your application's needs
        # Build Content-Security-Policy; allow embedding for voice-widget iframe route
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            # Allow websocket / http calls during development
            "connect-src 'self' http://localhost:3000 http://127.0.0.1:3000 ws://localhost:8000 wss://localhost:8000",
        ]

        # Only disallow embedding for non-widget pages
        if not request.url.path.startswith("/voice-widget/iframe"):
            csp_directives.append("frame-ancestors 'none'")

        csp_directives += [
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # HTTP Strict Transport Security (HSTS)
        # Only enable in production with HTTPS
        if os.getenv("ENVIRONMENT", "development") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # X-Content-Type-Options
        # Prevents browsers from MIME-sniffing a response away from the declared content-type
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options
        # Prevents clickjacking by disallowing your site to be embedded in iframes
        # response.headers["X-Frame-Options"] = "DENY"
        
        # Referrer-Policy
        # Controls how much referrer information is included with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions-Policy (formerly Feature-Policy)
        # Restricts which browser features can be used
        permissions_policy = [
            "geolocation=()",
            "microphone=*",  # allow microphone in iframe
            "camera=()",
            "payment=()"
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions_policy)
        
        # X-XSS-Protection
        # Enables XSS filtering in browsers that support it
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Ensure we're not overriding CORS headers
        if "Access-Control-Allow-Origin" not in response.headers:
            # Only add if not already set by CORS middleware
            origin = request.headers.get("Origin")
            if origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response     
