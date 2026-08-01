from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import webhooks

router = DefaultRouter()
router.register('', views.PaymentViewSet, basename='payment')

urlpatterns = [
    path('webhook/korapay/', webhooks.korapay_webhook, name='korapay-webhook'),
    path('', include(router.urls)),
]