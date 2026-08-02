# backend/rooms/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('', views.RoomViewSet, basename='room')

urlpatterns = [
    # Public endpoints (no auth required) MUST come before the router
    # include. DefaultRouter's detail route (^(?P<pk>[^/.]+)/$) would
    # otherwise match "public" as a pk and route it into RoomViewSet,
    # which requires authentication — that's what's causing the 401s.
    path('public/', views.public_rooms, name='public-rooms'),
    path('public/availability/', views.check_availability, name='check-availability'),
    path('public/<str:slug>/', views.public_room_detail, name='public-room-detail'),

    path('', include(router.urls)),
]