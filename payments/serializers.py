from rest_framework import serializers
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer"""
    
    class Meta:
        model = Payment
        fields = [
            'id', 'transaction_id', 'korapay_reference',
            'amount', 'currency', 'payment_method', 'payment_type',
            'status', 'sale', 'booking', 'checkin',
            'customer_name', 'customer_email', 'customer_phone',
            'description', 'metadata',
            'created_at', 'updated_at', 'paid_at', 'expires_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'paid_at']

class PaymentInitSerializer(serializers.Serializer):
    """Initialize payment serializer"""
    
    payment_type = serializers.ChoiceField(choices=Payment.PAYMENT_TYPE)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    sale_id = serializers.UUIDField(required=False)
    booking_id = serializers.UUIDField(required=False)
    checkin_id = serializers.UUIDField(required=False)
    customer_name = serializers.CharField(max_length=200, required=False)
    customer_email = serializers.EmailField(required=False)
    customer_phone = serializers.CharField(max_length=20, required=False)
    reference = serializers.CharField(max_length=100, required=False)
    callback_url = serializers.URLField(required=False)
    description = serializers.CharField(required=False)
    metadata = serializers.JSONField(required=False)
    
    def validate(self, data):
        """Validate that at least one related object is provided"""
        if not any([data.get('sale_id'), data.get('booking_id'), data.get('checkin_id')]):
            raise serializers.ValidationError(
                "At least one of sale_id, booking_id, or checkin_id is required"
            )
        return data

class PaymentVerifySerializer(serializers.Serializer):
    """Verify payment serializer"""
    reference = serializers.CharField(max_length=100)