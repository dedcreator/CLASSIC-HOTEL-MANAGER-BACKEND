# backend/menu/admin.py
from django.contrib import admin
from .models import Category, MenuItem, Order, OrderItem

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'sort_order']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    ordering = ['sort_order']

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'is_popular', 'is_new']
    list_filter = ['category', 'is_available', 'is_popular', 'is_new']
    search_fields = ['name', 'description']
    ordering = ['category', 'sort_order']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'table', 'customer_name', 'total_amount', 'status']
    list_filter = ['status', 'payment_status']
    search_fields = ['order_number', 'customer_name']

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['item_name', 'order', 'quantity', 'unit_price', 'subtotal']
    search_fields = ['item_name']