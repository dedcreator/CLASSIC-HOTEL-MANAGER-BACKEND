from rest_framework import serializers
from .models import PushSubscription, Notification


class PushSubscriptionSerializer(serializers.ModelSerializer):
    endpoint = serializers.CharField(required=True)
    p256dh = serializers.CharField(required=True)
    auth = serializers.CharField(required=True)
    user_agent = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = PushSubscription
        fields = ['id', 'endpoint', 'p256dh', 'auth', 'user_agent', 'created_at']
        read_only_fields = ['id', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
    is_read_by_me = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'role_target', 'title', 'message', 'notification_type',
            'data', 'link', 'is_read', 'is_read_by_me', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_is_read_by_me(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return obj.is_read
        if obj.user_id == request.user.id:
            return obj.is_read
        return obj.read_by.filter(id=request.user.id).exists()
