# backend/rooms/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Q
from .models import Room
from .serializers import RoomSerializer, RoomStatusSerializer, PublicRoomSerializer
import uuid

class RoomViewSet(viewsets.ModelViewSet):
    """ViewSet for managing rooms (admin/management)"""
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Room.objects.all()
        
        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
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
            room.status = new_status
            room.save()
            return Response({
                'status': 'success', 
                'new_status': room.status,
                'room': RoomSerializer(room).data
            })
        
        return Response(
            {'error': 'Invalid status'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        available_rooms = Room.objects.filter(status='available')
        serializer = self.get_serializer(available_rooms, many=True)
        return Response(serializer.data)


# ============ PUBLIC VIEWS (No Auth Required) ============

@api_view(['GET'])
@permission_classes([AllowAny])
def public_rooms(request):
    """Public endpoint for front-facing website"""
    rooms = Room.objects.all()
    
    # Filter by status (only show available and occupied for public)
    status = request.query_params.get('status')
    if status:
        rooms = rooms.filter(status=status)
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
                # Check if slug is a valid UUID
                uuid_obj = uuid.UUID(slug)
                room = Room.objects.get(
                    id=slug,
                    status__in=['available', 'occupied']
                )
            except (ValueError, TypeError):
                # Not a valid UUID, continue
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
    
    # For now, return available rooms without date filtering
    # (You can integrate with bookings later)
    rooms = Room.objects.filter(status='available')
    
    if room_type:
        rooms = rooms.filter(room_type=room_type)
    
    # Check if any rooms are available
    available_rooms = rooms.filter(status='available')
    
    return Response({
        'available': available_rooms.exists(),
        'available_count': available_rooms.count(),
        'room_types': list(available_rooms.values_list('room_type', flat=True).distinct()),
        'rooms': PublicRoomSerializer(available_rooms, many=True).data
    })