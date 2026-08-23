# backend/hotel_project/health.py
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from django.utils import timezone

@csrf_exempt
def health_check(request):
    """
    Public health check endpoint for Render keep-alive, UptimeRobot, and monitoring.
    Verifies system uptime and database connectivity.
    """
    db_status = "connected"
    try:
        connection.ensure_connection()
    except Exception as e:
        db_status = f"error: {str(e)}"
        return JsonResponse({
            "status": "unhealthy",
            "database": db_status,
            "timestamp": timezone.now().isoformat(),
            "service": "Classic Hotel Management API",
            "environment": "production" if os.environ.get("DEBUG", "True").lower() in ("false", "0") else "development",
        }, status=503)

    return JsonResponse({
        "status": "healthy",
        "database": db_status,
        "timestamp": timezone.now().isoformat(),
        "service": "Classic Hotel Management API",
        "version": "1.0.0",
        "environment": "production" if os.environ.get("DEBUG", "True").lower() in ("false", "0") else "development",
    }, status=200)
