# backend/menu/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db.models import Q, Sum
from django.utils import timezone
from .models import Category, MenuItem, Order, OrderItem
from .serializers import (
    CategorySerializer, MenuItemSerializer,
    OrderSerializer, CreateOrderSerializer, OrderStatusUpdateSerializer
)
import logging

logger = logging.getLogger(__name__)

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [AllowAny()]  # Allow public read access
    
    def get_queryset(self):
        queryset = Category.objects.all()
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        return queryset

class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [AllowAny()]  # Allow public read access
    
    def get_queryset(self):
        queryset = MenuItem.objects.all()
        
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)
        
        is_available = self.request.query_params.get('is_available')
        if is_available is not None:
            queryset = queryset.filter(is_available=is_available.lower() == 'true')
        
        is_popular = self.request.query_params.get('is_popular')
        if is_popular is not None:
            queryset = queryset.filter(is_popular=is_popular.lower() == 'true')
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def get_permissions(self):
        # Allow public access for viewing orders (customers need to see their orders)
        if self.action in ['list', 'retrieve', 'create']:
            return [AllowAny()]
        # Staff updates require authentication
        elif self.action in ['update_status']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateOrderSerializer
        return OrderSerializer
    
    def get_queryset(self):
        queryset = Order.objects.all()
        
        # Allow filtering by table for public access
        table = self.request.query_params.get('table')
        if table:
            queryset = queryset.filter(table_id=table)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(placed_at__date__gte=start_date, placed_at__date__lte=end_date)
        
        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        return queryset
    
    def perform_create(self, serializer):
        # Allow public order creation
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Update order status (requires authentication for staff)"""
        if not request.user.is_authenticated:
            return Response({
                'error': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        new_status = serializer.validated_data['status']
        notes = serializer.validated_data.get('notes', '')
        
        valid_transitions = {
            'pending': ['preparing', 'ready', 'served', 'paid', 'cancelled'],
            'preparing': ['ready', 'served', 'paid', 'cancelled'],
            'ready': ['served', 'paid', 'cancelled'],
            'served': ['paid', 'cancelled'],
            'paid': [],
            'cancelled': [],
        }
        
        if new_status not in valid_transitions.get(order.status, []):
            return Response({
                'error': f'Cannot transition from {order.status} to {new_status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        order.update_status(new_status, request.user)
        if new_status == 'paid':
            order.payment_status = 'paid'
            order.paid_at = timezone.now()
            order.save()
        
        if notes:
            order.notes = (order.notes + '\n' + notes) if order.notes else notes
            order.save()
        
        return Response({
            'success': True,
            'order': OrderSerializer(order).data,
            'message': f'Order status updated to {new_status}'
        })
    
    @action(detail=True, methods=['post'], permission_classes=[AllowAny])
    def pay(self, request, pk=None):
        """Customer or staff payment for an order"""
        order = self.get_object()
        payment_method = request.data.get('payment_method', 'korapay')
        payment_reference = request.data.get('payment_reference', '')
        
        order.status = 'paid'
        order.payment_status = 'paid'
        order.payment_method = payment_method
        order.paid_at = timezone.now()
        order.save()
        
        if payment_reference:
            from payments.models import Payment
            Payment.objects.update_or_create(
                transaction_id=payment_reference,
                defaults={
                    'amount': order.total_amount,
                    'payment_method': payment_method,
                    'payment_type': 'sale',
                    'status': 'completed',
                    'customer_name': order.customer_name or f"Table {order.table.table_number}",
                    'paid_at': timezone.now(),
                }
            )
            
        return Response({
            'success': True,
            'order': OrderSerializer(order).data,
            'message': 'Order paid successfully'
        })

    
    @action(detail=False, methods=['get'])
    def today(self, request):
        today = timezone.now().date()
        orders = Order.objects.filter(placed_at__date=today)
        
        return Response({
            'orders': OrderSerializer(orders, many=True).data,
            'count': orders.count(),
            'pending': orders.filter(status='pending').count(),
            'preparing': orders.filter(status='preparing').count(),
            'ready': orders.filter(status='ready').count(),
            'served': orders.filter(status='served').count(),
            'paid': orders.filter(status='paid').count(),
        })

# Public Menu Views (no auth required)
class PublicMenuViewSet(viewsets.ReadOnlyModelViewSet):
    """Public API for menu (no authentication required)"""
    queryset = MenuItem.objects.filter(is_available=True)
    serializer_class = MenuItemSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        queryset = MenuItem.objects.filter(is_available=True)
        
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category_id=category)
        
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset

class PublicCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public API for categories (no authentication required)"""
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]