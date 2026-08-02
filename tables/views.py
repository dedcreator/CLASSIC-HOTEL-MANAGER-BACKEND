# backend/tables/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from .models import Table
from .serializers import TableSerializer, CreateTableSerializer

class TableViewSet(viewsets.ModelViewSet):
    """ViewSet for managing tables (authenticated)"""
    queryset = Table.objects.all()
    serializer_class = TableSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateTableSerializer
        return TableSerializer
    
    def get_queryset(self):
        queryset = Table.objects.all()
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        section = self.request.query_params.get('section')
        if section:
            queryset = queryset.filter(section=section)
        
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(table_number__icontains=search) |
                Q(name__icontains=search) |
                Q(slug__icontains=search)
            )
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def generate_qr(self, request, pk=None):
        """Generate/Regenerate QR code for a table"""
        table = self.get_object()
        base_url = request.build_absolute_uri('/').rstrip('/')
        qr_code = table.generate_qr_code(base_url)
        table.qr_code = qr_code
        table.save()
        
        return Response({
            'success': True,
            'table_id': str(table.id),
            'table_number': table.table_number,
            'qr_code': qr_code,
            'menu_url': f"{base_url}/menu/{table.slug}"
        })
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update table status"""
        table = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in dict(Table.STATUS_CHOICES):
            return Response({
                'error': 'Invalid status'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        table.status = new_status
        table.save()
        
        return Response({
            'success': True,
            'table': TableSerializer(table).data
        })


# Use APIView for public endpoints - this is more reliable
class PublicTableListView(APIView):
    """Public API to list all active tables"""
    permission_classes = [AllowAny]
    authentication_classes = []  # Disable authentication
    
    def get(self, request):
        tables = Table.objects.filter(is_active=True)
        serializer = TableSerializer(tables, many=True)
        return Response(serializer.data)


class PublicTableDetailView(APIView):
    """Public API to get a single table by slug or id"""
    permission_classes = [AllowAny]
    authentication_classes = []  # Disable authentication
    
    def get(self, request, slug):
        try:
            table = Table.objects.get(
                Q(slug=slug) | Q(id=slug),
                is_active=True
            )
            serializer = TableSerializer(table)
            return Response(serializer.data)
        except Table.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound(detail="Table not found")


# Also keep the viewset for potential future use
class PublicTableViewSet(viewsets.ReadOnlyModelViewSet):
    """Public API for tables (no authentication required)"""
    permission_classes = [AllowAny]
    authentication_classes = []  # Disable authentication
    queryset = Table.objects.filter(is_active=True)
    serializer_class = TableSerializer
    lookup_field = 'slug'
    
    def get_queryset(self):
        queryset = Table.objects.filter(is_active=True)
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset

# backend/tables/views.py - Add this at the bottom

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

@api_view(['GET'])
@permission_classes([AllowAny])
def public_table_list(request):
    """Public API to list all active tables"""
    tables = Table.objects.filter(is_active=True)
    serializer = TableSerializer(tables, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def public_table_detail(request, slug):
    """Public API to get a single table by slug or id"""
    try:
        table = Table.objects.get(
            Q(slug=slug) | Q(id=slug),
            is_active=True
        )
        serializer = TableSerializer(table)
        return Response(serializer.data)
    except Table.DoesNotExist:
        from rest_framework.exceptions import NotFound
        raise NotFound(detail="Table not found")