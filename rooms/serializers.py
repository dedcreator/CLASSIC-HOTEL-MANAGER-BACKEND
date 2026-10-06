# backend/rooms/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Room, RoomAccessCode, SecurityAuditLog

class RoomAccessCodeSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    created_by_role = serializers.CharField(source='created_by.role', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    approved_by_role = serializers.CharField(source='approved_by.role', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)
    code_type_display = serializers.CharField(source='get_code_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RoomAccessCode
        fields = [
            'id', 'code', 'code_type', 'code_type_display',
            'room', 'room_number', 'booking', 'status', 'status_display',
            'is_valid', 'created_by', 'created_by_name', 'created_by_role',
            'approved_by', 'approved_by_name', 'approved_by_role',
            'approved_at', 'valid_from', 'valid_until', 'reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'code', 'created_at', 'updated_at', 'is_valid']


class SecurityAuditLogSerializer(serializers.ModelSerializer):
    actor_display = serializers.SerializerMethodField()
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = SecurityAuditLog
        fields = [
            'id', 'timestamp', 'actor', 'actor_username', 'actor_role',
            'actor_display', 'action', 'action_display',
            'room', 'room_number', 'booking', 'booking_reference',
            'access_code', 'details', 'ip_address'
        ]
        read_only_fields = fields

    def get_actor_display(self, obj):
        return f"{obj.actor_username} ({obj.actor_role})"


class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(source='get_room_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    active_access_code = serializers.SerializerMethodField()
    pending_cleaning_request = serializers.SerializerMethodField()
    
    class Meta:
        model = Room
        fields = [
            'id', 'room_number', 'room_type', 'room_type_display',
            'base_price', 'barcode', 'status', 'status_display',
            'description', 'capacity', 'name', 'size',
            'amenities', 'rating', 'review_count', 'is_featured',
            'slug', 'created_at', 'updated_at',
            'active_access_code', 'pending_cleaning_request'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'slug', 'active_access_code', 'pending_cleaning_request']

    def get_active_access_code(self, obj):
        now = timezone.now()
        active_code = obj.access_codes.filter(
            status='active',
            valid_until__gte=now
        ).order_by('-created_at').first()
        if active_code:
            return RoomAccessCodeSerializer(active_code).data
        return None

    def get_pending_cleaning_request(self, obj):
        pending = obj.access_codes.filter(
            code_type='cleaning',
            status='pending_approval'
        ).order_by('-created_at').first()
        if pending:
            return RoomAccessCodeSerializer(pending).data
        return None


class RoomStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ['id', 'room_number', 'status']


class PublicRoomSerializer(serializers.ModelSerializer):
    """Simplified serializer for public website"""
    room_type_display = serializers.CharField(source='get_room_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Room
        fields = [
            'id', 'room_number', 'room_type', 'room_type_display',
            'base_price', 'status', 'status_display',
            'description', 'capacity', 'name', 'size',
            'amenities', 'rating', 'review_count', 'is_featured',
            'slug'
        ]