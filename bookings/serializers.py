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
    active_access_code = serializers.SerializerMethodField()
    
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
            'active_access_code',
        ]
        read_only_fields = ['id', 'booking_reference', 'created_at', 'updated_at', 'checked_in_at', 'checked_out_at', 'active_access_code']
    
    def get_guest_name(self, obj):
        return f"{obj.guest.first_name} {obj.guest.last_name}"
    
    def get_room_number(self, obj):
        return obj.room.room_number
    
    def get_nights(self, obj):
        return obj.total_nights

    def get_active_access_code(self, obj):
        from rooms.serializers import RoomAccessCodeSerializer
        code = obj.access_codes.filter(status='active').order_by('-created_at').first()
        if code and code.is_valid:
            return RoomAccessCodeSerializer(code).data
        return None

class CreateBookingSerializer(serializers.ModelSerializer):
    guest = serializers.PrimaryKeyRelatedField(queryset=Guest.objects.all(), required=False)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False)
    guest_name = serializers.CharField(write_only=True, required=False)
    guest_email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    guest_phone = serializers.CharField(write_only=True, required=False, allow_blank=True)
    room_id = serializers.UUIDField(write_only=True, required=False)
    total_nights = serializers.IntegerField(required=False)
    notes = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference',
            'guest', 'room', 'guest_name', 'guest_email', 'guest_phone', 'room_id',
            'check_in', 'check_out', 
            'adults', 'children', 'total_nights', 'total_amount',
            'special_requests', 'notes', 'status', 'payment_status'
        ]
        read_only_fields = ['id', 'booking_reference']
    
    def create(self, validated_data):
        guest = validated_data.get('guest')
        guest_name = validated_data.pop('guest_name', None)
        guest_email = validated_data.pop('guest_email', '')
        guest_phone = validated_data.pop('guest_phone', '')
        room = validated_data.get('room')
        room_id = validated_data.pop('room_id', None)
        notes = validated_data.pop('notes', '')
        
        # Handle guest
        if not guest and guest_name:
            name_parts = guest_name.strip().split()
            first_name = name_parts[0] if name_parts else 'Guest'
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'Visitor'
            guest = Guest.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=guest_email or f"{first_name.lower()}@guest.com",
                phone=guest_phone or '0000000000',
            )
            validated_data['guest'] = guest
        elif not guest:
            # Fallback guest if none provided
            guest, _ = Guest.objects.get_or_create(
                email='walkin@tsghotel.com.ng',
                defaults={'first_name': 'Walk-in', 'last_name': 'Guest', 'phone': '0000000000'}
            )
            validated_data['guest'] = guest
            
        # Handle room
        if not room and room_id:
            try:
                room = Room.objects.get(id=room_id)
                validated_data['room'] = room
            except Room.DoesNotExist:
                raise serializers.ValidationError({'room': 'Room not found'})
        
        # Calculate nights
        check_in = validated_data.get('check_in')
        check_out = validated_data.get('check_out')
        if check_in and check_out:
            nights = (check_out - check_in).days
            if nights <= 0:
                nights = 1
            validated_data['total_nights'] = validated_data.get('total_nights') or nights
            
            # Calculate total amount
            if not validated_data.get('total_amount') and room:
                validated_data['total_amount'] = room.base_price * nights
        
        if notes and not validated_data.get('special_requests'):
            validated_data['special_requests'] = notes
            
        booking = Booking.objects.create(**validated_data)
        return booking

class CheckInSerializer(serializers.Serializer):
    """Serializer for check-in with payment processing"""
    payment_method = serializers.ChoiceField(
        choices=['korapay', 'cash', 'card', 'transfer'],
        default='korapay'
    )
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    payment_reference = serializers.CharField(max_length=100, required=False, allow_null=True)
    
    def validate(self, data):
        """Validate the check-in data"""
        payment_method = data.get('payment_method', 'korapay')
        if payment_method not in ['korapay', 'cash', 'card', 'transfer']:
            raise serializers.ValidationError({
                'payment_method': f'Invalid payment method: {payment_method}'
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