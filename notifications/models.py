from django.db import models
from django.conf import settings
import uuid


class PushSubscription(models.Model):
    """
    Stores Web Push API subscriptions for devices registered by users.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_subscriptions',
        null=True,
        blank=True
    )
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField(help_text="Client public key (p256dh)")
    auth = models.TextField(help_text="Client authentication secret (auth)")
    user_agent = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        username = self.user.username if self.user else "Anonymous"
        return f"PushSubscription for {username} ({self.endpoint[:35]}...)"


class Notification(models.Model):
    """
    Stores in-app notifications for individual users or specific staff roles.
    """
    NOTIFICATION_TYPES = (
        ('room_checkout', 'Room Check-Out'),
        ('website_booking', 'Website Booking'),
        ('stock_added', 'Stock Added'),
        ('system', 'System Alert'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='in_app_notifications',
        null=True,
        blank=True,
        help_text="Direct recipient user (if null, role_target applies to all users with that role)"
    )
    role_target = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Target role (e.g. RECEPTIONIST, HOUSEKEEPING, CEO, ALL)"
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES,
        default='system'
    )
    data = models.JSONField(default=dict, blank=True)
    link = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='read_role_notifications',
        help_text="Tracks users who have acknowledged/read this notification"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.user.username if self.user else f"Role:{self.role_target}"
        return f"[{self.notification_type}] {self.title} -> {target}"
