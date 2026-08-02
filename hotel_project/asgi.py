"""
ASGI config for hotel_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

# backend/hotel_project/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path
from menu.consumers import OrderConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter([
                path('ws/orders/', OrderConsumer.as_asgi()),
                path('ws/orders/<str:table_id>/', OrderConsumer.as_asgi()),
            ])
        )
    ),
})
