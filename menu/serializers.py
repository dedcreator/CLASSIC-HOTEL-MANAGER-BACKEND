# backend/menu/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from decimal import Decimal
from .models import Category, MenuItem, Order, OrderItem
from tables.models import Table  # Import Table from tables app

User = get_user_model()

class CategorySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'icon', 'sort_order', 
            'is_active', 'item_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_item_count(self, obj):
        return obj.items.filter(is_available=True).count()

class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    dietary_tags = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItem
        fields = [
            'id', 'name', 'description', 'price', 'category', 'category_name',
            'is_vegetarian', 'is_gluten_free', 'is_vegan',
            'is_available', 'is_popular', 'is_new',
            'preparation_time', 'image', 'icon_name',
            'sort_order', 'dietary_tags', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_dietary_tags(self, obj):
        return obj.dietary_tags

class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = [
            'id', 'table_number', 'name', 'slug', 'capacity',
            'status', 'section', 'floor', 'is_active',
            'qr_code', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            'id', 'menu_item', 'item_name', 'quantity', 
            'unit_price', 'subtotal', 'special_instructions'
        ]
        read_only_fields = ['id', 'subtotal']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(source='order_items', many=True, read_only=True)
    table_number = serializers.CharField(source='table.table_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'table', 'table_number',
            'customer_name', 'customer_email', 'customer_phone',
            'items', 'subtotal', 'tax', 'total_amount',
            'status', 'status_display', 'payment_status', 'payment_method',
            'placed_at', 'updated_at', 'prepared_at', 'served_at', 'paid_at',
            'notes', 'special_instructions'
        ]
        read_only_fields = ['id', 'order_number', 'placed_at', 'updated_at']

class CreateOrderSerializer(serializers.ModelSerializer):
    items = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=True
    )
    
    class Meta:
        model = Order
        fields = [
            'table', 'customer_name', 'customer_email', 'customer_phone',
            'items', 'notes', 'special_instructions'
        ]
    
    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        
        for item in value:
            if 'menu_item_id' not in item:
                raise serializers.ValidationError("Each item must have a menu_item_id")
            if 'quantity' not in item or item['quantity'] < 1:
                raise serializers.ValidationError("Each item must have a valid quantity")
        
        return value
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        table = validated_data.get('table')
        
        # Calculate totals
        subtotal = Decimal('0')
        order_items = []
        
        for item_data in items_data:
            menu_item_id = item_data.get('menu_item_id')
            quantity = item_data.get('quantity', 1)
            special_instructions = item_data.get('special_instructions', '')
            
            # Get menu item
            from .models import MenuItem
            try:
                menu_item = MenuItem.objects.get(id=menu_item_id)
            except MenuItem.DoesNotExist:
                raise serializers.ValidationError(f"Menu item {menu_item_id} not found")
            
            unit_price = menu_item.price
            item_subtotal = unit_price * quantity
            subtotal += item_subtotal
            
            order_items.append({
                'menu_item': menu_item,
                'item_name': menu_item.name,
                'quantity': quantity,
                'unit_price': unit_price,
                'subtotal': item_subtotal,
                'special_instructions': special_instructions,
            })
        
        # Calculate tax (7.5%)
        tax = subtotal * Decimal('0.075')
        total = subtotal + tax
        
        # Create order
        order = Order.objects.create(
            subtotal=subtotal,
            tax=tax,
            total_amount=total,
            **validated_data
        )
        
        # Create order items
        for item_data in order_items:
            OrderItem.objects.create(order=order, **item_data)
        
        return order

class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)