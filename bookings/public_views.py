# backend/bookings/public_views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
import json
import datetime
from .models import Guest, Booking
from rooms.models import Room

@csrf_exempt
@require_http_methods(["POST"])
def create_booking(request):
    """Public endpoint for creating bookings"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required = ['name', 'email', 'phone', 'roomType', 'checkIn', 'checkOut']
        for field in required:
            if not data.get(field):
                return JsonResponse({'error': f'{field} required'}, status=400)
        
        # Split name
        name_parts = data['name'].strip().split()
        first_name = name_parts[0] if name_parts else 'Guest'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        
        # Parse dates
        check_in = datetime.datetime.strptime(data['checkIn'], '%Y-%m-%d').date()
        check_out = datetime.datetime.strptime(data['checkOut'], '%Y-%m-%d').date()
        
        with transaction.atomic():
            # Create guest
            guest = Guest.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=data['email'],
                phone=data['phone'],
            )
            
            # Find available room
            room = Room.objects.filter(
                room_type=data['roomType'],
                status='available'
            ).first()
            
            if not room:
                return JsonResponse({'error': 'No rooms available'}, status=400)
            
            # Calculate nights
            nights = (check_out - check_in).days
            
            # Create booking
            booking = Booking.objects.create(
                guest=guest,
                room=room,
                check_in=check_in,
                check_out=check_out,
                adults=data.get('adults', 1),
                children=data.get('children', 0),
                total_nights=nights,
                total_amount=data.get('totalAmount', 0),
                special_requests=data.get('specialRequests', ''),
                status='confirmed',
                payment_status='pending'
            )
            
            return JsonResponse({
                'success': True,
                'booking_reference': booking.booking_reference,
                'room_number': room.room_number
            }, status=201)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def check_availability(request):
    """
    Check room availability. Response shape matches what the frontend
    (hotel-website/app/booking/page.tsx) expects:
      { available, available_rooms, room_types, rooms: [...] }
    Previously this returned {available, count} only, which is why the
    frontend always showed "no rooms available" even on a 200 response.
    """
    check_in = request.GET.get('check_in')
    check_out = request.GET.get('check_out')
    room_type = request.GET.get('room_type')  # was previously read but never used

    if not check_in or not check_out:
        return JsonResponse({'error': 'Dates required'}, status=400)

    try:
        check_in_date = datetime.datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.datetime.strptime(check_out, '%Y-%m-%d').date()

        # Start with all available rooms
        rooms_qs = Room.objects.filter(status='available')

        # Apply room_type filter if the frontend sent one
        if room_type:
            rooms_qs = rooms_qs.filter(room_type=room_type)

        # Exclude rooms with a conflicting booking for these dates
        booked_ids = Booking.objects.filter(
            check_in__lt=check_out_date,
            check_out__gt=check_in_date,
            status__in=['confirmed', 'checked_in']
        ).values_list('room_id', flat=True)

        available_rooms = rooms_qs.exclude(id__in=booked_ids)

        # room_types should reflect what's available across ALL types,
        # not just the filtered one, so the "no rooms of X, but Y is free"
        # messaging on the frontend has something useful to show.
        all_available_types = Room.objects.filter(
            status='available'
        ).exclude(id__in=booked_ids).values_list('room_type', flat=True).distinct()

        return JsonResponse({
            'available': available_rooms.exists(),
            'available_rooms': available_rooms.count(),
            'room_types': list(all_available_types),
            'rooms': [
                {
                    'id': str(room.id),
                    'room_number': room.room_number,
                    'room_type': room.room_type,
                    'base_price': float(room.base_price),
                    'name': room.name,
                }
                for room in available_rooms[:5]
            ],
        })
    except ValueError as e:
        # e.g. bad date format
        return JsonResponse({'error': f'Invalid date: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def test(request):
    """Test endpoint"""
    return JsonResponse({
        'status': 'ok',
        'method': request.method,
        'message': 'Public endpoint working'
    })