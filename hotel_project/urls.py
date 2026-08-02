# backend/hotel_project/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from inventory.views import (
    ProductViewSet, BatchViewSet, 
    StockMovementViewSet, StockAlertViewSet
)
from sales.views import SaleViewSet

router = DefaultRouter()
router.register('products', ProductViewSet)
router.register('batches', BatchViewSet)
router.register('stock-movements', StockMovementViewSet)
router.register('stock-alerts', StockAlertViewSet)
router.register('sales', SaleViewSet)

urlpatterns = [
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