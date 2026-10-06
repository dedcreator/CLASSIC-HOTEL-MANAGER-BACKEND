# backend/inventory/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from rest_framework.permissions import AllowAny 
from .models import Product, Batch, StockMovement, StockAlert
from .serializers import (
    ProductSerializer, BatchSerializer, 
    StockMovementSerializer, StockAlertSerializer,
    SimpleProductSerializer, AddStockSerializer
)


class IsCEO(permissions.BasePermission):
    """CEO-only permission - case insensitive"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Convert role to uppercase for comparison
        role = request.user.role.upper() if request.user.role else ''
        return role == 'CEO'


class ProductViewSet(viewsets.ModelViewSet):
    """
    Manage products
    """
    queryset = Product.objects.filter(is_active=True).order_by('name')
    serializer_class = ProductSerializer
    
    def perform_destroy(self, instance):
        # Soft delete - just mark as inactive
        instance.is_active = False
        instance.save()
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to return proper response and only CEO can delete"""
        instance = self.get_object()
        
        # Check if user is CEO (case insensitive)
        user_role = request.user.role.upper() if request.user.role else ''
        if user_role != 'CEO':
            return Response(
                {'error': 'Only CEO can delete products'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        self.perform_destroy(instance)
        return Response(
            {'message': 'Product deleted successfully'},
            status=status.HTTP_200_OK
        )

    def get_permissions(self):
        """Only CEO can delete products"""
        if self.action == 'destroy':
            return [IsCEO()]
        return [permissions.IsAuthenticated()]
    
    def get_queryset(self):
        queryset = Product.objects.filter(is_active=True)
        
        # Filter by category
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Search by name or barcode
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(barcode__icontains=search)
            )
        
        # Filter by location (bar/lounge/both)
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(location=location)
        
        return queryset
    
    def perform_create(self, serializer):
        product = serializer.save(created_by=self.request.user)
        if product.total_stock > 0:
            try:
                from notifications.services import notify_stock_added
                notify_stock_added(
                    product=product,
                    batch=None,
                    user=self.request.user,
                    quantity=product.total_stock
                )
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Failed to dispatch stock added notification: {notif_err}")
    
    @action(detail=False, methods=['get'])
    def simple_list(self, request):
        """Get simplified product list"""
        products = self.get_queryset()
        serializer = SimpleProductSerializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def scan(self, request):
        """Look up product by barcode"""
        barcode = request.query_params.get('barcode')
        if not barcode:
            return Response(
                {'error': 'Barcode required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(barcode=barcode, is_active=True)
            serializer = self.get_serializer(product)
            return Response(serializer.data)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def add_stock(self, request, pk=None):
        """Add stock to a product"""
        product = self.get_object()
        
        serializer = AddStockSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        # Create new batch
        batch = Batch.objects.create(
            product=product,
            quantity=data['quantity'],
            remaining_quantity=data['quantity'],
            cost_price=data.get('cost_price'),
            selling_price=data.get('selling_price', product.default_price),
            supplier=data.get('supplier', ''),
            batch_number=data.get('batch_number', ''),
            notes=data.get('notes', ''),
            received_by=request.user
        )
        
        # Update product total_stock (database field)
        product.total_stock += data['quantity']
        product.save()
        
        # Record movement
        StockMovement.objects.create(
            product=product,
            batch=batch,
            quantity=data['quantity'],
            movement_type='restock',
            price_at_movement=data.get('selling_price', product.default_price),
            created_by=request.user,
            notes=f"Restocked: {data['quantity']} units"
        )
        
        # Resolve any low stock alerts
        if product.total_stock > product.min_stock_level:
            StockAlert.objects.filter(
                product=product,
                is_resolved=False
            ).update(
                is_resolved=True,
                resolved_at=timezone.now(),
                resolved_by=request.user
            )

        # Trigger CEO push and email notification
        try:
            from notifications.services import notify_stock_added
            notify_stock_added(
                product=product,
                batch=batch,
                user=request.user,
                quantity=data['quantity']
            )
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).error(f"Failed to dispatch stock added notification: {notif_err}")
        
        return Response(BatchSerializer(batch).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get stock movement history"""
        product = self.get_object()
        
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        movements = StockMovement.objects.filter(
            product=product,
            created_at__gte=start_date
        ).order_by('-created_at')
        
        batches = Batch.objects.filter(
            product=product,
            quantity__gt=0
        ).order_by('-date_received')
        
        return Response({
            'product': {
                'id': product.id,
                'name': product.name,
                'total_stock': product.total_stock,
                'min_stock_level': product.min_stock_level,
                'is_low_stock': product.is_low_stock
            },
            'movements': StockMovementSerializer(movements, many=True).data,
            'active_batches': BatchSerializer(batches, many=True).data
        })


class BatchViewSet(viewsets.ModelViewSet):
    """
    Manage inventory batches
    """
    queryset = Batch.objects.all().order_by('-date_received')
    serializer_class = BatchSerializer
    
    def get_queryset(self):
        queryset = Batch.objects.all()
        
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        in_stock = self.request.query_params.get('in_stock')
        if in_stock and in_stock.lower() == 'true':
            queryset = queryset.filter(quantity__gt=0)
        
        return queryset


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    View stock movements
    """
    queryset = StockMovement.objects.all().order_by('-created_at')
    serializer_class = StockMovementSerializer
    
    def get_queryset(self):
        queryset = StockMovement.objects.all()
        
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        movement_type = self.request.query_params.get('type')
        if movement_type:
            queryset = queryset.filter(movement_type=movement_type)
        
        return queryset


class StockAlertViewSet(viewsets.ModelViewSet):
    """
    View and manage low stock alerts
    """
    queryset = StockAlert.objects.all().order_by('-created_at')
    serializer_class = StockAlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = StockAlert.objects.all()
        
        resolved = self.request.query_params.get('resolved')
        if resolved is not None:
            is_resolved = resolved.lower() == 'true'
            queryset = queryset.filter(is_resolved=is_resolved)
        
        # Filter by product
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def check_all(self, request):
        """Check all products for low stock"""
        products = Product.objects.filter(is_active=True)
        new_alerts = []
        updated_alerts = []
        
        for product in products:
            if product.is_low_stock:
                alert, created = StockAlert.objects.get_or_create(
                    product=product,
                    is_resolved=False,
                    defaults={
                        'threshold': product.min_stock_level,
                        'current_stock': product.total_stock
                    }
                )
                
                if created:
                    new_alerts.append(alert)
                elif alert.current_stock != product.total_stock:
                    alert.current_stock = product.total_stock
                    alert.save()
                    updated_alerts.append(alert)
            else:
                # Resolve any active alerts for this product
                StockAlert.objects.filter(
                    product=product,
                    is_resolved=False
                ).update(
                    is_resolved=True,
                    resolved_at=timezone.now()
                )
        
        return Response({
            'message': f'Created {len(new_alerts)} new alerts, updated {len(updated_alerts)} existing alerts',
            'new_alerts': StockAlertSerializer(new_alerts, many=True).data,
            'updated_alerts': StockAlertSerializer(updated_alerts, many=True).data
        })
    
    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Mark an alert as resolved"""
        alert = self.get_object()
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        
        serializer = self.get_serializer(alert)
        return Response(serializer.data)