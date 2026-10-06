from django.urls import path
from .views import (
    VapidPublicKeyView,
    PushSubscribeView,
    PushUnsubscribeView,
    PushTestView,
    NotificationListView,
    NotificationUnreadCountView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)

urlpatterns = [
    path('vapid-public-key/', VapidPublicKeyView.as_view(), name='vapid-public-key'),
    path('subscribe/', PushSubscribeView.as_view(), name='push-subscribe'),
    path('unsubscribe/', PushUnsubscribeView.as_view(), name='push-unsubscribe'),
    path('test-push/', PushTestView.as_view(), name='test-push'),
    path('', NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountView.as_view(), name='notification-unread-count'),
    path('<uuid:pk>/read/', NotificationMarkReadView.as_view(), name='notification-mark-read'),
    path('mark-all-read/', NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
]
