# backend/bookings/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.models import AnonymousUser

class PublicBypassMiddleware(MiddlewareMixin):
    """
    Completely bypass authentication and CSRF for public endpoints
    """
    PUBLIC_PREFIXES = (
        '/api/bookings/public/',
        '/api/menu/public/',
        '/api/tables/public/',
        '/api/payments/webhook/',
    )

    def process_request(self, request):
        if any(request.path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
            # Set a flag to skip all CSRF checks
            request._dont_enforce_csrf_checks = True
            # Ensure user is anonymous if not authenticated
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                request.user = AnonymousUser()
        return None