# backend/sales/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Sale, SaleItem, Customer, SavedCart
from inventory.serializers import ProductSerializer
from decimal import Decimal, ROUND_HALF_UP

class SaleItemSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = SaleItem
        fields = '__all__'

class SaleSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    staff_name = serializers.CharField(source='staff.username', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    
    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ['transaction_number', 'created_at']
    
    def get_items(self, obj):
        items = obj.items.all()
        return SaleItemSerializer(items, many=True).data

class CreateSaleSerializer(serializers.Serializer):
    guest_name = serializers.CharField(required=False, allow_blank=True, default="Walk-in Guest")
    room_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(choices=['cash', 'card', 'transfer', 'korapay', 'bank_transfer', 'room_charge'], default='cash')
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    customer_email = serializers.EmailField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    payment_reference = serializers.CharField(required=False, allow_blank=True)
    payment_channel = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = serializers.ListField(
        child=serializers.DictField()
    )
    
    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("At least one item is required")
        return items
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        amount_paid = validated_data.pop('amount_paid', Decimal('0'))
        room_id = validated_data.pop('room_id', None)
        customer_email = validated_data.pop('customer_email', '')
        customer_phone = validated_data.pop('customer_phone', '')
        payment_reference = validated_data.pop('payment_reference', '')
        payment_channel = validated_data.pop('payment_channel', '')
        
        # Get staff from context
        request = self.context.get('request')
        staff = request.user if (request and hasattr(request, 'user') and request.user.is_authenticated) else None
        
        # Determine payment status
        payment_method = validated_data.get('payment_method', 'cash')
        payment_status = 'paid' if (payment_reference or payment_method in ['cash', 'card', 'transfer', 'bank_transfer', 'room_charge']) else 'pending'
        
        # Create sale
        sale = Sale.objects.create(
            staff=staff,
            amount_paid=amount_paid,
            payment_status=payment_status,
            **validated_data
        )
        
        # Handle room
        if room_id:
            from rooms.models import Room
            try:
                sale.room = Room.objects.get(id=room_id)
                sale.save()
            except Room.DoesNotExist:
                pass
        
        # Create sale items
        for item_data in items_data:
            SaleItem.objects.create(
                sale=sale,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                discount=item_data.get('discount', 0)
            )
        
        # Refresh sale to get updated totals
        sale.refresh_from_db()
        
        # Calculate change for cash payments
        if payment_method == 'cash' and amount_paid > sale.total_amount:
            sale.change = amount_paid - sale.total_amount
            sale.save()
        
        # If payment_reference is present, update or create Payment record
        if payment_reference:
            from payments.models import Payment
            Payment.objects.update_or_create(
                transaction_id=payment_reference,
                defaults={
                    'amount': sale.total_amount,
                    'payment_method': payment_method,
                    'payment_type': 'sale',
                    'status': 'completed',
                    'sale': sale,
                    'customer_name': sale.guest_name,
                    'customer_email': customer_email,
                    'customer_phone': customer_phone,
                    'paid_at': timezone.now(),
                }
            )
        
        return sale

    def to_representation(self, instance):
        # Use SaleSerializer to return the response instead of CreateSaleSerializer
        return SaleSerializer(instance, context=self.context).data


class TodaySummarySerializer(serializers.Serializer):
    total_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_transactions = serializers.IntegerField()
    cash_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    card_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    room_charges = serializers.DecimalField(max_digits=10, decimal_places=2)

class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = '__all__'
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

class SavedCartSerializer(serializers.ModelSerializer):
    customer_details = CustomerSerializer(source='customer', read_only=True)
    
    class Meta:
        model = SavedCart
        fields = '__all__'

class CreateSavedCartSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField(required=False)
    customer_data = serializers.DictField(required=False)
    cart_items = serializers.ListField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        if not data.get('customer_id') and not data.get('customer_data'):
            raise serializers.ValidationError("Either customer_id or customer_data is required")
        if not data.get('cart_items'):
            raise serializers.ValidationError("Cart items are required")
        return data
    
    def create(self, validated_data):
        if validated_data.get('customer_id'):
            customer = Customer.objects.get(id=validated_data['customer_id'])
        else:
            customer_data = validated_data['customer_data']
            customer, created = Customer.objects.get_or_create(
                email=customer_data.get('email'),
                defaults={
                    'first_name': customer_data.get('first_name', ''),
                    'last_name': customer_data.get('last_name', ''),
                    'phone': customer_data.get('phone', ''),
                }
            )
        
        subtotal = sum(item['quantity'] * item['unit_price'] for item in validated_data['cart_items'])
        tax = subtotal * Decimal('0.075')
        total = subtotal + tax
        
        cart = SavedCart.objects.create(
            customer=customer,
            cart_data=validated_data['cart_items'],
            subtotal=subtotal,
            tax=tax,
            total=total,
            notes=validated_data.get('notes', '')
        )
        
        return cart