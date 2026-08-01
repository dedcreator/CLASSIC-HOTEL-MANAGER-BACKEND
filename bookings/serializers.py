# backend/bookings/serializers.py
from rest_framework import serializers
from .models import Guest, Booking
from rooms.models import Room
from rooms.serializers import RoomSerializer

class GuestSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Guest
        fields = ['id', 'first_name', 'last_name', 'full_name', 'email', 'phone', 'id_number', 'address', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

class BookingSerializer(serializers.ModelSerializer):
    guest_details = GuestSerializer(source='guest', read_only=True)
    room_details = RoomSerializer(source='room', read_only=True)
    guest_name = serializers.SerializerMethodField()
    room_number = serializers.SerializerMethodField()
    nights = serializers.SerializerMethodField()
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'guest', 'guest_details', 'guest_name',
            'room', 'room_details', 'room_number', 'nights',
            'check_in', 'check_out', 
            'adults', 'children', 'total_nights',
            'total_amount', 'amount_paid',
            'payment_method', 'payment_status',
            'status', 'special_requests',
            'checked_in_at', 'checked_out_at',
            'created_at', 'updated_at', 'created_by',
        ]
        read_only_fields = ['id', 'booking_reference', 'created_at', 'updated_at', 'checked_in_at', 'checked_out_at']
    
    def get_guest_name(self, obj):
        return f"{obj.guest.first_name} {obj.guest.last_name}"
    
    def get_room_number(self, obj):
        return obj.room.room_number
    
    def get_nights(self, obj):
        return obj.total_nights

class CreateBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'guest', 'room', 'check_in', 'check_out', 
            'adults', 'children', 'total_nights', 'total_amount',
            'special_requests', 'status', 'payment_status'
        ]
    
    def create(self, validated_data):
        print("Creating booking with data:", validated_data)
        booking = Booking.objects.create(**validated_data)
        print("Created booking:", booking.id, booking.booking_reference)
        return booking

class CheckInSerializer(serializers.Serializer):
    """Serializer for check-in with Korapay payment only"""
    payment_method = serializers.CharField(max_length=20, default='korapay')
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    payment_reference = serializers.CharField(max_length=100, required=False, allow_null=True)
    
    def validate(self, data):
        """Validate the check-in data"""
        payment_method = data.get('payment_method', 'korapay')
        
        # Only allow Korapay (cashless)
        if payment_method != 'korapay':
            raise serializers.ValidationError({
                'payment_method': 'Only Korapay payments are accepted (cashless)'
            })
        
        return data

class CheckOutSerializer(serializers.Serializer):
    additional_charges = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = serializers.CharField(max_length=500, required=False)

class SimpleBookingSerializer(serializers.ModelSerializer):
    guest_name = serializers.CharField(source='guest.__str__', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    
    class Meta:
        model = Booking
        fields = ['id', 'booking_reference', 'guest_name', 'room_number', 
                  'check_in', 'check_out', 'status', 'total_amount', 'payment_status']