# backend/rooms/serializers.py
from rest_framework import serializers
from .models import Room

class RoomSerializer(serializers.ModelSerializer):
    room_type_display = serializers.CharField(source='get_room_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Room
        fields = [
            'id', 'room_number', 'room_type', 'room_type_display',
            'base_price', 'barcode', 'status', 'status_display',
            'description', 'capacity', 'name', 'size',
            'amenities', 'rating', 'review_count', 'is_featured',
            'slug', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'slug']

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