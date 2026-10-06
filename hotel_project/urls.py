# backend/hotel_project/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventory.views import (
    ProductViewSet, BatchViewSet, 
    StockMovementViewSet, StockAlertViewSet
)
from sales.views import SaleViewSet
from .health import health_check

router = DefaultRouter()
router.register('products', ProductViewSet)
router.register('batches', BatchViewSet)
router.register('stock-movements', StockMovementViewSet)
router.register('stock-alerts', StockAlertViewSet)
router.register('sales', SaleViewSet)

urlpatterns = [
    # Health Check endpoints for UptimeRobot & Render
    path('health/', health_check, name='health_check'),
    path('health', health_check, name='health_check_no_slash'),
    path('api/health/', health_check, name='api_health_check'),
    path('api/health', health_check, name='api_health_check_no_slash'),

    path('admin/', admin.site.urls),
    
    # API routes
    path('api/', include(router.urls)),
    
    # Accounts app (authentication and user management)
    path('api/auth/', include('accounts.urls')),
    
    # Other app routes
    path('api/inventory/', include('inventory.urls')),
    path('api/rooms/', include('rooms.urls')),
    path('api/bookings/', include('bookings.urls')), 
    path('api/reports/', include('reports.urls')), 
    path('api/sales/', include('sales.urls')),
    path('api/consumables/', include('consumables.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/menu/', include('menu.urls')),  
    path('api/tables/', include('tables.urls')),
    path('api/notifications/', include('notifications.urls')),
]

# DRF Settings - Add DEFAULT_PERMISSION_CLASSES
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    # Add this - default to authenticated for all views
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}