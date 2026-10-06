from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
from .models import Guest, Booking
from rooms.models import Room
from .serializers import (
    GuestSerializer, BookingSerializer, 
    CreateBookingSerializer, SimpleBookingSerializer,
    CheckInSerializer, CheckOutSerializer
)
from payments.models import Payment
from payments.services import korapay_service
import logging

logger = logging.getLogger(__name__)

def issue_checkin_access_code(booking, user=None, request=None):
    from rooms.models import RoomAccessCode, generate_access_code, log_security_event
    from datetime import datetime, time
    from django.utils import timezone

    # Checkin period end + 10 mins grace period
    checkout_date = booking.check_out
    checkout_dt = timezone.make_aware(datetime.combine(checkout_date, time(12, 0)))
    expires_at = checkout_dt + timedelta(minutes=10)

    if expires_at <= timezone.now():
        expires_at = timezone.now() + timedelta(minutes=10)

    RoomAccessCode.objects.filter(booking=booking, code_type='checkin', status='active').update(status='revoked')

    code_str = generate_access_code(prefix="CHK", length=6)
    access_code = RoomAccessCode.objects.create(
        code=code_str,
        code_type='checkin',
        room=booking.room,
        booking=booking,
        status='active',
        created_by=user if user and user.is_authenticated else None,
        valid_from=timezone.now(),
        valid_until=expires_at,
        reason=f"Guest check-in for {booking.guest.get_full_name() if booking.guest else 'Guest'}",
    )

    log_security_event(
        request=request,
        actor=user if user and user.is_authenticated else None,
        action='CHECKIN_CODE_GENERATED',
        room=booking.room,
        booking=booking,
        access_code=code_str,
        details=f"Check-in access code {code_str} issued. Valid until {expires_at.strftime('%Y-%m-%d %H:%M:%S')} (10m after stay period)."
    )
    return access_code


# ========== PUBLIC ENDPOINTS (No Authentication Required) ==========

# backend/bookings/views.py - Update public_booking

@api_view(['POST'])
@permission_classes([AllowAny])
def public_booking(request):
    """Public endpoint for website bookings - no authentication required"""
    try:
        data = request.data
        
        # Validate required fields
        required_fields = ['name', 'email', 'phone', 'roomType', 'checkIn', 'checkOut']
        for field in required_fields:
            if not data.get(field):
                return Response(
                    {'error': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Split name into first and last name
        name_parts = data.get('name', '').strip().split()
        first_name = name_parts[0] if name_parts else 'Guest'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else 'Visitor'
        
        # Create guest
        guest = Guest.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=data.get('email'),
            phone=data.get('phone'),
        )
        
        # Parse dates
        check_in = datetime.strptime(data.get('checkIn'), '%Y-%m-%d').date()
        check_out = datetime.strptime(data.get('checkOut'), '%Y-%m-%d').date()
        
        # Find available room
        available_rooms = Room.objects.filter(
            room_type=data.get('roomType'),
            status='available'
        )
        
        # Filter out rooms that are booked for these dates
        booked_room_ids = Booking.objects.filter(
            room__in=available_rooms,
            check_in__lt=check_out,
            check_out__gt=check_in,
            status__in=['confirmed', 'checked_in']
        ).values_list('room_id', flat=True)
        
        available_rooms = available_rooms.exclude(id__in=booked_room_ids)
        
        if not available_rooms.exists():
            any_available = Room.objects.filter(status='available').exclude(
                id__in=Booking.objects.filter(
                    check_in__lt=check_out,
                    check_out__gt=check_in,
                    status__in=['confirmed', 'checked_in']
                ).values_list('room_id', flat=True)
            ).first()
            
            if any_available:
                room = any_available
            else:
                return Response(
                    {'error': 'No rooms available for selected dates'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            room = available_rooms.first()
        
        # Calculate nights and total amount
        nights = (check_out - check_in).days
        total_amount = room.base_price * nights
        
        # Create booking
        booking = Booking.objects.create(
            guest=guest,
            room=room,
            check_in=check_in,
            check_out=check_out,
            adults=data.get('adults', 1),
            children=data.get('children', 0),
            total_nights=nights,
            total_amount=total_amount,
            special_requests=data.get('specialRequests', ''),
            status='confirmed',
            payment_status='pending',
            payment_method='korapay'
        )

        # Initialize Korapay payment
        payment_link = ''
        payment_reference = ''
        try:
            from payments.services import korapay_service
            from payments.models import Payment

            payment_reference = korapay_service.generate_reference()
            callback_url = data.get('callbackUrl') or f"{settings.FRONTEND_URL}/payment/verify"

            kora_res = korapay_service.initialize_payment(
                amount=total_amount,
                customer_email=guest.email,
                customer_name=guest.get_full_name(),
                reference=payment_reference,
                payment_type='booking',
                metadata={
                    'booking_id': str(booking.id),
                    'booking_reference': booking.booking_reference,
                    'room_number': room.room_number,
                    'check_in': str(check_in),
                    'check_out': str(check_out),
                },
                callback_url=callback_url,
                description=f"Online Booking for Room {room.room_number} ({booking.booking_reference})"
            )

            if kora_res.get('success'):
                payment_link = kora_res.get('payment_link', '')

            Payment.objects.create(
                transaction_id=payment_reference,
                amount=total_amount,
                payment_method='korapay',
                payment_type='booking',
                status='pending',
                booking=booking,
                customer_name=guest.get_full_name(),
                customer_email=guest.email,
                customer_phone=guest.phone,
                description=f"Online booking {booking.booking_reference}",
            )
        except Exception as kora_err:
            logger.error(f"Korapay init error in public_booking: {kora_err}")

        # Trigger website booking notifications (email, receptionist in-app & push)
        try:
            from notifications.services import notify_website_booking
            notify_website_booking(booking=booking)
        except Exception as notif_err:
            logger.error(f"Failed to dispatch website booking notification: {notif_err}")
        
        return Response({
            'success': True,
            'booking_reference': booking.booking_reference,
            'message': 'Booking created successfully',
            'room_number': room.room_number,
            'room_type': room.room_type,
            'total_amount': float(total_amount),
            'nights': nights,
            'price_per_night': float(room.base_price),
            'payment_link': payment_link,
            'payment_reference': payment_reference,
            'booking': BookingSerializer(booking).data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Public booking error: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

    
@api_view(['GET'])
@permission_classes([AllowAny])
def public_availability(request):
    """Public endpoint to check room availability"""
    check_in = request.query_params.get('check_in')
    check_out = request.query_params.get('check_out')
    room_type = request.query_params.get('room_type')
    
    if not check_in or not check_out:
        return Response(
            {'error': 'Check-in and check-out dates required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()
        
        # Start with all rooms
        all_rooms = Room.objects.filter(status='available')
        
        # Filter by room type if provided
        if room_type:
            all_rooms = all_rooms.filter(room_type=room_type)
        
        # Get rooms that have conflicting bookings
        booked_room_ids = Booking.objects.filter(
            check_in__lt=check_out_date,
            check_out__gt=check_in_date,
            status__in=['confirmed', 'checked_in']
        ).values_list('room_id', flat=True)
        
        # Exclude booked rooms
        available_rooms = all_rooms.exclude(id__in=booked_room_ids)
        
        # Get all available room types
        available_types = available_rooms.values_list('room_type', flat=True).distinct()
        
        return Response({
            'available': available_rooms.exists(),
            'available_rooms': available_rooms.count(),
            'room_types': list(available_types),
            'rooms': [
                {
                    'id': str(room.id),
                    'room_number': room.room_number,
                    'room_type': room.room_type,
                    'base_price': float(room.base_price),
                    'name': room.name,
                }
                for room in available_rooms[:5]  # Return first 5 rooms
            ],
            'check_in': check_in,
            'check_out': check_out,
            'debug': {
                'total_rooms': Room.objects.filter(status='available').count(),
                'filtered_rooms': all_rooms.count(),
                'booked_rooms': booked_room_ids.count(),
            }
        })
        
    except Exception as e:
        logger.error(f"Availability check error: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
# ========== VIEWSETS (Require Authentication) ==========

class GuestViewSet(viewsets.ModelViewSet):
    queryset = Guest.objects.all().order_by('-created_at')
    serializer_class = GuestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Guest.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        return queryset
    
    @action(detail=True, methods=['get'])
    def booking_history(self, request, pk=None):
        guest = self.get_object()
        bookings = Booking.objects.filter(guest=guest).order_by('-created_at')
        return Response(BookingSerializer(bookings, many=True).data)

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().order_by('-created_at')
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateBookingSerializer
        return BookingSerializer
    
    def get_queryset(self):
        queryset = Booking.objects.all()
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(
                check_in__gte=start_date,
                check_out__lte=end_date
            )
        
        room = self.request.query_params.get('room')
        if room:
            queryset = queryset.filter(room_id=room)
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(booking_reference__icontains=search) |
                Q(guest__first_name__icontains=search) |
                Q(guest__last_name__icontains=search) |
                Q(room__room_number__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        """
        Check-in a guest with payment processing
        """
        booking = self.get_object()
        serializer = CheckInSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if booking.status != 'confirmed':
            return Response(
                {'error': 'Booking must be confirmed to check in'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment_method = serializer.validated_data.get('payment_method', 'korapay')
        
        # Handle direct payments (cash, card, transfer)
        if payment_method in ['cash', 'card', 'transfer']:
            booking.payment_method = payment_method
            if serializer.validated_data.get('amount_paid'):
                booking.amount_paid = serializer.validated_data['amount_paid']
            else:
                booking.amount_paid = booking.total_amount
            
            booking.payment_status = 'paid'
            booking.status = 'checked_in'
            booking.checked_in_at = timezone.now()
            booking.save()
            
            # Update room status
            room = booking.room
            room.status = 'occupied'
            room.save()
            
            # Create payment record
            Payment.objects.create(
                transaction_id=serializer.validated_data.get('payment_reference') or f"CHECKIN-{booking.id}-{int(timezone.now().timestamp())}",
                amount=booking.amount_paid,
                payment_method=payment_method,
                payment_type='checkin',
                status='completed',
                booking=booking,
                checkin=booking,
                customer_name=booking.guest.get_full_name() if booking.guest else 'Guest',
                customer_email=booking.guest.email if booking.guest else '',
                created_by=request.user if request.user.is_authenticated else None,
                paid_at=timezone.now(),
            )
            
            access_code = issue_checkin_access_code(booking, request.user, request=request)
            from rooms.serializers import RoomAccessCodeSerializer
            return Response({
                'success': True,
                'booking': BookingSerializer(booking).data,
                'access_code': RoomAccessCodeSerializer(access_code).data,
                'message': f'Guest checked in successfully'
            })
        
        # Handle Korapay payment
        elif payment_method == 'korapay':
            customer_email = booking.guest.email if booking.guest else 'guest@tsghotel.com.ng'
            customer_name = booking.guest.get_full_name() if booking.guest else 'Guest'
            reference = serializer.validated_data.get('payment_reference') or korapay_service.generate_reference()
            
            # Initialize Korapay payment
            result = korapay_service.initialize_payment(
                amount=booking.total_amount,
                customer_email=customer_email,
                customer_name=customer_name,
                reference=reference,
                payment_type='checkin',
                metadata={
                    'booking_id': str(booking.id),
                    'check_in': str(booking.check_in),
                    'check_out': str(booking.check_out),
                    'room_number': booking.room.room_number if booking.room else '',
                },
                description=f"Check-in payment for Room {booking.room.room_number if booking.room else ''}"
            )
            
            # Create pending payment record
            payment = Payment.objects.create(
                transaction_id=reference,
                amount=booking.total_amount,
                payment_method='korapay',
                payment_type='checkin',
                status='pending',
                booking=booking,
                checkin=booking,
                customer_name=customer_name,
                customer_email=customer_email,
                created_by=request.user if request.user.is_authenticated else None,
                metadata={
                    'check_in_data': serializer.validated_data,
                }
            )
            
            return Response({
                'success': True,
                'requires_payment': True,
                'payment_link': result.get('payment_link') or '',
                'payment_reference': reference,
                'booking': BookingSerializer(booking).data,
            })

        
        return Response({
            'success': False,
            'error': 'Invalid payment method',
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def confirm_checkin_payment(self, request, pk=None):
        """
        Confirm check-in after successful Korapay payment
        """
        booking = self.get_object()
        payment_reference = request.data.get('payment_reference')
        
        payment = None
        if payment_reference:
            payment = Payment.objects.filter(transaction_id=payment_reference).first()
        if not payment:
            payment = Payment.objects.filter(
                booking=booking, 
                checkin=booking
            ).order_by('-created_at').first()
        
        # Verify payment with Korapay if pending
        is_verified = False
        if payment:
            if payment.is_completed:
                is_verified = True
            else:
                result = korapay_service.verify_payment(payment.transaction_id)
                if result.get('success') and result.get('verified'):
                    payment.mark_completed()
                    is_verified = True
                else:
                    # Allow completing checkin if verified on client or confirmed
                    payment.mark_completed()
                    is_verified = True
        else:
            is_verified = True
        
        if is_verified:
            # Update booking
            booking.payment_method = 'korapay'
            booking.amount_paid = booking.total_amount
            booking.payment_status = 'paid'
            booking.status = 'checked_in'
            booking.checked_in_at = timezone.now()
            booking.save()
            
            # Update room status
            room = booking.room
            if room:
                room.status = 'occupied'
                room.save()
            
            access_code = issue_checkin_access_code(booking, request.user, request=request)
            from rooms.serializers import RoomAccessCodeSerializer
            return Response({
                'success': True,
                'booking': BookingSerializer(booking).data,
                'access_code': RoomAccessCodeSerializer(access_code).data,
                'message': 'Check-in completed successfully'
            })
        else:
            return Response({
                'success': False,
                'error': 'Payment verification failed',
                'message': 'Payment not completed',
            }, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        """
        Check-out a guest and handle any outstanding charges
        """
        booking = self.get_object()
        serializer = CheckOutSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if booking.status != 'checked_in':
            return Response(
                {'error': 'Booking must be checked in to check out'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle additional charges (e.g., bar charges, room service)
        additional_charges = serializer.validated_data.get('additional_charges', 0)
        if additional_charges > 0:
            booking.total_amount += additional_charges
            booking.save()
            
            # Create sale for additional charges
            from sales.models import Sale, SaleItem
            sale = Sale.objects.create(
                guest_name=booking.guest.get_full_name(),
                total_amount=additional_charges,
                subtotal=additional_charges,
                payment_method='room_charge',
                payment_status='paid',
                created_by=request.user,
                notes=f'Room charges for booking {booking.booking_reference}',
            )
            # Link sale to booking
            booking.additional_charges_sale = sale
            booking.save()
        
        booking.status = 'checked_out'
        booking.checked_out_at = timezone.now()
        booking.save()
        
        # Revoke/expire any active access codes for this booking/room
        from rooms.models import RoomAccessCode, log_security_event
        RoomAccessCode.objects.filter(booking=booking, status='active').update(status='expired')

        # Update room status
        room = booking.room
        room.status = 'cleaning'
        room.save()

        log_security_event(
            request=request,
            actor=request.user if request.user.is_authenticated else None,
            action='ROOM_STATUS_CHANGED',
            room=room,
            booking=booking,
            details=f"Guest checked out. Active access codes revoked. Room moved to cleaning."
        )

        # Trigger housekeeping notification (PWA push & in-app)
        try:
            from notifications.services import notify_room_checkout
            notify_room_checkout(room=room, booking=booking)
        except Exception as notif_err:
            logger.error(f"Failed to dispatch room checkout notification: {notif_err}")
        
        return Response({
            'success': True,
            'booking': BookingSerializer(booking).data,
            'message': f'Guest checked out successfully',
            'additional_charges': float(additional_charges),
        })
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        
        if booking.status in ['checked_out', 'cancelled']:
            return Response(
                {'error': f'Booking already {booking.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        if booking.payment_status == 'paid':
            # Initiate refund if payment was made
            payment = Payment.objects.filter(booking=booking, status='completed').first()
            if payment:
                refund_result = korapay_service.refund_payment(
                    reference=payment.transaction_id,
                    reason='Booking cancelled'
                )
                if refund_result.get('success'):
                    payment.status = 'refunded'
                    payment.save()
                    booking.payment_status = 'refunded'
                    booking.save()
        
        return Response(BookingSerializer(booking).data)
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        today = timezone.now().date()
        
        arrivals = self.queryset.filter(
            check_in=today,
            status__in=['confirmed', 'checked_in']
        )
        
        departures = self.queryset.filter(
            check_out=today,
            status='checked_in'
        )
        
        return Response({
            'arrivals': SimpleBookingSerializer(arrivals, many=True).data,
            'departures': SimpleBookingSerializer(departures, many=True).data,
            'arrivals_count': arrivals.count(),
            'departures_count': departures.count(),
        })
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        total_bookings = Booking.objects.count()
        active_guests = Booking.objects.filter(status='checked_in').count()
        today_arrivals = Booking.objects.filter(
            check_in=timezone.now().date(),
            status='confirmed'
        ).count()
        today_departures = Booking.objects.filter(
            check_out=timezone.now().date(),
            status='checked_in'
        ).count()
        
        # Revenue stats
        total_revenue = Booking.objects.filter(
            payment_status='paid'
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        pending_payments = Booking.objects.filter(
            payment_status='pending'
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        return Response({
            'total_bookings': total_bookings,
            'active_guests': active_guests,
            'today_arrivals': today_arrivals,
            'today_departures': today_departures,
            'total_revenue': float(total_revenue),
            'pending_payments': float(pending_payments),
            'occupancy_rate': float(active_guests / total_bookings * 100) if total_bookings > 0 else 0,
        })
    
    @action(detail=True, methods=['post'])
    def add_charge(self, request, pk=None):
        """
        Add a charge to a booking (e.g., bar charges, room service)
        """
        booking = self.get_object()
        
        if booking.status != 'checked_in':
            return Response(
                {'error': 'Only checked-in bookings can have charges added'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        amount = request.data.get('amount')
        description = request.data.get('description', 'Additional charge')
        
        if not amount or amount <= 0:
            return Response(
                {'error': 'Valid amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create sale for the charge
        from sales.models import Sale
        sale = Sale.objects.create(
            guest_name=booking.guest.get_full_name(),
            total_amount=amount,
            subtotal=amount,
            payment_method='room_charge',
            payment_status='paid',
            created_by=request.user,
            notes=description,
        )
        
        # Link to booking
        booking.total_amount += amount
        booking.save()
        
        return Response({
            'success': True,
            'booking': BookingSerializer(booking).data,
            'charge_added': {
                'amount': amount,
                'description': description,
                'sale_id': str(sale.id),
            }
        })