# backend/tables/serializers.py
from rest_framework import serializers
from .models import Table

class TableSerializer(serializers.ModelSerializer):
    qr_code_url = serializers.SerializerMethodField()
    menu_url = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Table
        fields = [
            'id', 'table_number', 'name', 'slug', 'capacity', 
            'status', 'section', 'floor', 'is_active',
            'qr_code', 'qr_code_url', 'menu_url',
            'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
    
    def get_qr_code_url(self, obj):
        if obj.qr_code:
            return obj.qr_code
        return obj.generate_qr_code()
    
    def get_menu_url(self, obj):
        from django.conf import settings
        base_url = getattr(settings, 'BASE_URL', 'https://yourdomain.com')
        return f"{base_url}/menu/{obj.slug}"
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.username
        return None

class CreateTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = [
            'table_number', 'name', 'capacity', 
            'status', 'section', 'floor', 'is_active'
        ]