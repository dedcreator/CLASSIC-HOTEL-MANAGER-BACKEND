# backend/tables/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Table

@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ['table_number', 'name', 'slug', 'capacity', 'status', 'section', 'is_active']
    list_filter = ['status', 'section', 'is_active']
    search_fields = ['table_number', 'name', 'slug']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at', 'qr_code_preview']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('table_number', 'name', 'slug', 'capacity')
        }),
        ('Location', {
            'fields': ('section', 'floor')
        }),
        ('Status', {
            'fields': ('status', 'is_active')
        }),
        ('QR Code', {
            'fields': ('qr_code', 'qr_code_preview'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        })
    )
    
    def qr_code_preview(self, obj):
        if obj.qr_code:
            return format_html('<img src="{}" width="100" height="100" />', obj.qr_code)
        return '-'
    qr_code_preview.short_description = 'QR Code Preview'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)