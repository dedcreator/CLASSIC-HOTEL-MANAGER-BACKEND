# backend/rooms/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import uuid
import logging

from .models import Room, RoomAccessCode, SecurityAuditLog, generate_access_code, log_security_event
from .serializers import (
    RoomSerializer, RoomStatusSerializer, PublicRoomSerializer,
    RoomAccessCodeSerializer, SecurityAuditLogSerializer
)

logger = logging.getLogger(__name__)

class RoomViewSet(viewsets.ModelViewSet):
    """ViewSet for managing rooms (admin/management)"""
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Room.objects.all()
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        
        # Filter by room type
        room_type = self.request.query_params.get('room_type')
        if room_type:
            queryset = queryset.filter(room_type=room_type)
        
        # Filter by featured
        is_featured = self.request.query_params.get('is_featured')
        if is_featured is not None:
            queryset = queryset.filter(is_featured=is_featured.lower() == 'true')
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(room_number__icontains=search) |
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        room = self.get_object()
        new_status = request.data.get('status')
        
        if new_status in dict(Room.STATUS_CHOICES):
            old_status = room.status
            room.status = new_status
            room.save()

            log_security_event(
                request=request,
                action='ROOM_STATUS_CHANGED',
                room=room,
                details=f"Room status changed from {old_status} to {new_status}."
            )

            if new_status == 'cleaning' and old_status != 'cleaning':
                try:
                    from notifications.services import notify_room_checkout
                    notify_room_checkout(room=room)
                except Exception as notif_err:
                    logger.error(f"Failed to dispatch room checkout notification: {notif_err}")

            return Response({
                'status': 'success', 
                'new_status': room.status,
                'room': RoomSerializer(room).data
            })
        
        return Response(
            {'error': 'Invalid status'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['get'])
    def access_codes(self, request, pk=None):
        room = self.get_object()
        codes = room.access_codes.all().order_by('-created_at')
        return Response(RoomAccessCodeSerializer(codes, many=True).data)

    @action(detail=True, methods=['get'])
    def audit_logs(self, request, pk=None):
        room = self.get_object()
        logs = room.security_audit_logs.all().order_by('-timestamp')[:50]
        return Response(SecurityAuditLogSerializer(logs, many=True).data)

    @action(detail=False, methods=['get'])
    def available(self, request):
        available_rooms = Room.objects.filter(status='available')
        serializer = self.get_serializer(available_rooms, many=True)
        return Response(serializer.data)


class RoomAccessCodeViewSet(viewsets.ModelViewSet):
    """
    Zero-Trust access code management:
    - Check-in codes (valid during stay + 10 mins grace)
    - 1-hour Emergency override keys (Manager & CEO only)
    - Housekeeping cleaning access keys (requested by staff, approved by Manager/CEO, activated to ready)
    """
    queryset = RoomAccessCode.objects.all()
    serializer_class = RoomAccessCodeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = RoomAccessCode.objects.all()
        room_id = self.request.query_params.get('room')
        code_type = self.request.query_params.get('code_type')
        code_status = self.request.query_params.get('status')
        
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        if code_type:
            queryset = queryset.filter(code_type=code_type)
        if code_status:
            queryset = queryset.filter(status=code_status)

        return queryset

    @action(detail=False, methods=['post'])
    def create_emergency(self, request):
        """
        Manager and CEO can create a 1-hour emergency key for a room / checkin
        """
        user_role = getattr(request.user, 'role', '')
        if user_role not in ['CEO', 'MANAGER', 'ADMIN'] and not request.user.is_superuser:
            return Response(
                {'error': 'Permission denied. Only Manager or CEO can issue 1-hour emergency keys.'},
                status=status.HTTP_403_FORBIDDEN
            )

        room_id = request.data.get('room_id')
        booking_id = request.data.get('booking_id')
        reason = request.data.get('reason', '').strip()

        if not room_id:
            return Response({'error': 'room_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not reason:
            return Response({'error': 'A specific operational or emergency reason is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)

        booking = None
        if booking_id:
            from bookings.models import Booking
            booking = Booking.objects.filter(id=booking_id).first()

        now = timezone.now()
        expires_at = now + timedelta(hours=1) # Strictly 1 hour
        code_str = generate_access_code(prefix="EMG", length=6)

        access_code = RoomAccessCode.objects.create(
            code=code_str,
            code_type='emergency',
            room=room,
            booking=booking,
            status='active',
            created_by=request.user,
            approved_by=request.user,
            approved_at=now,
            valid_from=now,
            valid_until=expires_at,
            reason=reason
        )

        log_security_event(
            request=request,
            action='EMERGENCY_CODE_GENERATED',
            room=room,
            booking=booking,
            access_code=code_str,
            details=f"1-Hour Emergency override key issued by {user_role} {request.user.username}. Reason: {reason}."
        )

        return Response({
            'success': True,
            'message': f'Emergency 1-hour key issued for Room {room.room_number}',
            'access_code': RoomAccessCodeSerializer(access_code).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def request_cleaning(self, request):
        """
        Housekeeping requests a cleaning access key to clean a room
        """
        room_id = request.data.get('room_id')
        notes = request.data.get('notes', '').strip()

        if not room_id:
            return Response({'error': 'room_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Ensure room is set to cleaning status
        if room.status != 'cleaning':
            room.status = 'cleaning'
            room.save()

        # Check for existing pending request
        existing_pending = RoomAccessCode.objects.filter(
            room=room,
            code_type='cleaning',
            status='pending_approval'
        ).first()

        if existing_pending:
            return Response({
                'success': True,
                'message': 'A cleaning key request is already pending approval.',
                'access_code': RoomAccessCodeSerializer(existing_pending).data
            })

        now = timezone.now()
        code_str = generate_access_code(prefix="CLN", length=6)

        access_code = RoomAccessCode.objects.create(
            code=code_str,
            code_type='cleaning',
            room=room,
            status='pending_approval',
            created_by=request.user,
            valid_from=now,
            valid_until=now + timedelta(hours=3),
            reason=notes or f"Room cleaning request by {request.user.username}"
        )

        log_security_event(
            request=request,
            action='CLEANING_CODE_REQUESTED',
            room=room,
            access_code=code_str,
            details=f"Cleaning access key requested by {getattr(request.user, 'role', 'STAFF')} {request.user.username}."
        )

        return Response({
            'success': True,
            'message': f'Cleaning access key requested for Room {room.room_number}. Awaiting manager approval.',
            'access_code': RoomAccessCodeSerializer(access_code).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def approve_cleaning(self, request, pk=None):
        """
        Manager or CEO approves a cleaning access key
        """
        user_role = getattr(request.user, 'role', '')
        if user_role not in ['CEO', 'MANAGER', 'ADMIN'] and not request.user.is_superuser:
            return Response(
                {'error': 'Permission denied. Only Manager or CEO can approve cleaning access keys.'},
                status=status.HTTP_403_FORBIDDEN
            )

        access_code = self.get_object()
        if access_code.code_type != 'cleaning':
            return Response({'error': 'This access code is not a cleaning request.'}, status=status.HTTP_400_BAD_REQUEST)

        if access_code.status != 'pending_approval':
            return Response({'error': f'Request is already {access_code.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        access_code.status = 'active'
        access_code.approved_by = request.user
        access_code.approved_at = now
        access_code.valid_from = now
        access_code.valid_until = now + timedelta(hours=2) # 2-hour cleaning validity
        access_code.save()

        log_security_event(
            request=request,
            action='CLEANING_CODE_APPROVED',
            room=access_code.room,
            access_code=access_code.code,
            details=f"Cleaning access key {access_code.code} approved by {user_role} {request.user.username}. Valid for 2 hours."
        )

        return Response({
            'success': True,
            'message': f'Cleaning access key approved for Room {access_code.room.room_number}.',
            'access_code': RoomAccessCodeSerializer(access_code).data
        })

    @action(detail=True, methods=['post'])
    def reject_cleaning(self, request, pk=None):
        """
        Manager or CEO rejects a cleaning key request
        """
        user_role = getattr(request.user, 'role', '')
        if user_role not in ['CEO', 'MANAGER', 'ADMIN'] and not request.user.is_superuser:
            return Response({'error': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        access_code = self.get_object()
        access_code.status = 'revoked'
        access_code.save()

        log_security_event(
            request=request,
            action='CLEANING_CODE_REJECTED',
            room=access_code.room,
            access_code=access_code.code,
            details=f"Cleaning access key rejected by {user_role} {request.user.username}."
        )

        return Response({
            'success': True,
            'message': 'Cleaning key request rejected.'
        })

    @action(detail=True, methods=['post'])
    def activate_room(self, request, pk=None):
        """
        Complete cleaning and activate room to 'available'
        """
        access_code = self.get_object()
        room = access_code.room

        if access_code.code_type != 'cleaning':
            return Response({'error': 'Must be a cleaning access key to activate room.'}, status=status.HTTP_400_BAD_REQUEST)

        if access_code.status != 'active':
            return Response({'error': f'Key status is {access_code.status}, not active.'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        if access_code.valid_until < now:
            access_code.status = 'expired'
            access_code.save()
            return Response({'error': 'Cleaning key has expired. Please request a new key.'}, status=status.HTTP_400_BAD_REQUEST)

        # Mark key as used/completed
        access_code.status = 'used'
        access_code.save()

        # Update room to available
        room.status = 'available'
        room.save()

        user_role = getattr(request.user, 'role', 'STAFF')
        log_security_event(
            request=request,
            action='ROOM_CLEANED_ACTIVATED',
            room=room,
            access_code=access_code.code,
            details=f"Room {room.room_number} cleaning finished. Room activated to Available by {request.user.username} ({user_role})."
        )

        return Response({
            'success': True,
            'message': f'Room {room.room_number} successfully cleaned and activated to Available.',
            'room': RoomSerializer(room).data,
            'access_code': RoomAccessCodeSerializer(access_code).data
        })

    @action(detail=False, methods=['post'])
    def verify(self, request):
        """
        Zero-Trust Code Verification: Verify if access code is valid for room
        """
        code_input = request.data.get('code', '').strip().upper()
        room_id = request.data.get('room_id')

        if not code_input:
            return Response({'valid': False, 'error': 'Code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = RoomAccessCode.objects.filter(code=code_input)
        if room_id:
            queryset = queryset.filter(room_id=room_id)

        access_code = queryset.first()
        if not access_code:
            log_security_event(
                request=request,
                action='ACCESS_CODE_VERIFIED',
                access_code=code_input,
                details=f"Failed verification attempt with non-existent code {code_input}."
            )
            return Response({'valid': False, 'error': 'Invalid access code.'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        if access_code.status != 'active' or access_code.valid_until < now:
            if access_code.status == 'active' and access_code.valid_until < now:
                access_code.status = 'expired'
                access_code.save()

            log_security_event(
                request=request,
                action='ACCESS_CODE_VERIFIED',
                room=access_code.room,
                access_code=code_input,
                details=f"Denied entry. Code {code_input} is expired or inactive ({access_code.status})."
            )
            return Response({
                'valid': False,
                'status': access_code.status,
                'error': f'Code is {access_code.status}.'
            }, status=status.HTTP_403_FORBIDDEN)

        log_security_event(
            request=request,
            action='ACCESS_CODE_VERIFIED',
            room=access_code.room,
            booking=access_code.booking,
            access_code=code_input,
            details=f"Successful access code verification for Room {access_code.room.room_number} ({access_code.code_type})."
        )

        return Response({
            'valid': True,
            'room_number': access_code.room.room_number,
            'code_type': access_code.code_type,
            'valid_until': access_code.valid_until,
            'message': 'Access granted'
        })


class SecurityAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit log viewset providing full zero-trust trail
    """
    queryset = SecurityAuditLog.objects.all()
    serializer_class = SecurityAuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = SecurityAuditLog.objects.all()
        room_id = self.request.query_params.get('room')
        room_number = self.request.query_params.get('room_number')
        action_param = self.request.query_params.get('action')
        actor = self.request.query_params.get('actor')
        search = self.request.query_params.get('search')

        if room_id:
            queryset = queryset.filter(room_id=room_id)
        if room_number:
            queryset = queryset.filter(room_number=room_number)
        if action_param:
            queryset = queryset.filter(action=action_param)
        if actor:
            queryset = queryset.filter(actor_username__icontains=actor)
        if search:
            queryset = queryset.filter(
                Q(details__icontains=search) |
                Q(actor_username__icontains=search) |
                Q(room_number__icontains=search) |
                Q(access_code__icontains=search)
            )

        return queryset


# ============ PUBLIC VIEWS (No Auth Required) ============

@api_view(['GET'])
@permission_classes([AllowAny])
def public_rooms(request):
    """Public endpoint for front-facing website"""
    rooms = Room.objects.all()
    
    # Filter by status (only show available and occupied for public)
    status_param = request.query_params.get('status')
    if status_param:
        rooms = rooms.filter(status=status_param)
    else:
        # Default: show available rooms only
        rooms = rooms.filter(status='available')
    
    # Filter by room type
    room_type = request.query_params.get('room_type')
    if room_type:
        rooms = rooms.filter(room_type=room_type)
    
    # Filter by featured
    is_featured = request.query_params.get('is_featured')
    if is_featured is not None:
        rooms = rooms.filter(is_featured=is_featured.lower() == 'true')
    
    # Search
    search = request.query_params.get('search')
    if search:
        rooms = rooms.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Order by price
    ordering = request.query_params.get('ordering', 'base_price')
    if ordering in ['base_price', '-base_price', 'rating', '-rating']:
        rooms = rooms.order_by(ordering)
    else:
        rooms = rooms.order_by('base_price')
    
    serializer = PublicRoomSerializer(rooms, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def public_room_detail(request, slug):
    """Public endpoint for single room detail - lookup by slug OR id"""
    try:
        room = None
        
        # First try to find by slug
        try:
            room = Room.objects.get(
                slug=slug,
                status__in=['available', 'occupied']
            )
        except Room.DoesNotExist:
            # If not found by slug, try by ID (if it's a valid UUID)
            try:
                uuid_obj = uuid.UUID(slug)
                room = Room.objects.get(
                    id=slug,
                    status__in=['available', 'occupied']
                )
            except (ValueError, TypeError):
                pass
            except Room.DoesNotExist:
                pass
        
        if room is None:
            return Response(
                {'error': 'Room not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = PublicRoomSerializer(room)
        return Response(serializer.data)
        
    except Exception as e:
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def check_availability(request):
    """Check room availability for specific dates"""
    check_in = request.query_params.get('check_in')
    check_out = request.query_params.get('check_out')
    room_type = request.query_params.get('room_type')
    
    if not check_in or not check_out:
        return Response(
            {'error': 'Check-in and check-out dates required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    rooms = Room.objects.filter(status='available')
    
    if room_type:
        rooms = rooms.filter(room_type=room_type)
    
    available_rooms = rooms.filter(status='available')
    
    return Response({
        'available': available_rooms.exists(),
        'available_count': available_rooms.count(),
        'room_types': list(available_rooms.values_list('room_type', flat=True).distinct()),
        'rooms': PublicRoomSerializer(available_rooms, many=True).data
    })