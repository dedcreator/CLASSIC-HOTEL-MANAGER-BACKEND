from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Sale, Customer, SavedCart, SaleItem
from .serializers import (
    SaleSerializer, CreateSaleSerializer, TodaySummarySerializer,
    CustomerSerializer, SavedCartSerializer, CreateSavedCartSerializer,
    SaleItemSerializer
)
from payments.models import Payment
from payments.services import korapay_service
import logging

logger = logging.getLogger(__name__)

class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all().order_by('-created_at')
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateSaleSerializer
        return SaleSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context
    
    def perform_create(self, serializer):
        serializer.save()
    
    @action(detail=False, methods=['post'])
    def create_with_payment(self, request):
        """
        Create a sale with payment processing
        Supports both cash and card/Korapay payments
        """
        serializer = CreateSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        payment_method = data.get('payment_method', 'cash')
        
        # Calculate totals
        items = data.get('items', [])
        subtotal = sum(item.get('unit_price', 0) * item.get('quantity', 0) for item in items)
        discount = data.get('discount', 0)
        tax = data.get('tax', 0)
        total = subtotal - discount + tax
        
        # Create sale first
        sale = Sale.objects.create(
            guest_name=data.get('guest_name', 'Walk-in Guest'),
            total_amount=total,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            payment_method=payment_method,
            payment_status='pending' if payment_method in ['card', 'korapay'] else 'paid',
            created_by=request.user,
            notes=data.get('notes', ''),
        )
        
        # Create sale items
        for item in items:
            SaleItem.objects.create(
                sale=sale,
                product_id=item.get('product_id'),
                product_name=item.get('product_name', ''),
                quantity=item.get('quantity', 0),
                unit_price=item.get('unit_price', 0),
                discount=item.get('discount', 0),
            )
        
        # Handle payment
        if payment_method in ['cash', 'card']:
            # Cash or card payment (already paid)
            sale.payment_status = 'paid'
            sale.save()
            
            # Create payment record
            Payment.objects.create(
                transaction_id=f"SALE-{sale.id}",
                amount=total,
                payment_method=payment_method,
                payment_type='sale',
                status='completed',
                sale=sale,
                customer_name=sale.guest_name,
                created_by=request.user,
                paid_at=timezone.now(),
            )
            
            return Response({
                'success': True,
                'sale': SaleSerializer(sale).data,
                'message': 'Sale completed successfully'
            }, status=status.HTTP_201_CREATED)
        
        elif payment_method == 'korapay':
            # Initialize Korapay payment
            result = korapay_service.initialize_payment(
                amount=total,
                customer_email=data.get('customer_email', ''),
                customer_name=sale.guest_name,
                payment_type='sale',
                metadata={
                    'sale_id': str(sale.id),
                    'items': len(items),
                },
                description=f"Bar sale - {len(items)} items"
            )
            
            if result.get('success'):
                # Create payment record
                payment = Payment.objects.create(
                    transaction_id=result['reference'],
                    amount=total,
                    payment_method='korapay',
                    payment_type='sale',
                    status='pending',
                    sale=sale,
                    customer_name=sale.guest_name,
                    customer_email=data.get('customer_email', ''),
                    created_by=request.user,
                    metadata={'sale_items': items},
                )
                
                return Response({
                    'success': True,
                    'requires_payment': True,
                    'payment_link': result['payment_link'],
                    'payment_reference': result['reference'],
                    'sale': SaleSerializer(sale).data,
                })
            else:
                # If payment fails, delete the sale
                sale.delete()
                return Response({
                    'success': False,
                    'error': 'Payment initialization failed',
                    'message': result.get('message'),
                }, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            'success': False,
            'error': 'Invalid payment method',
        }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        """
        Confirm payment for a sale after successful Korapay payment
        """
        sale = self.get_object()
        payment = Payment.objects.filter(sale=sale, status='pending').first()
        
        if not payment:
            return Response({
                'success': False,
                'error': 'No pending payment found for this sale'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Verify payment with Korapay
        result = korapay_service.verify_payment(payment.transaction_id)
        
        if result.get('success') and result.get('verified'):
            # Update payment and sale
            payment.mark_completed()
            sale.payment_status = 'paid'
            sale.save()
            
            return Response({
                'success': True,
                'sale': SaleSerializer(sale).data,
                'message': 'Payment confirmed successfully'
            })
        else:
            return Response({
                'success': False,
                'error': 'Payment verification failed',
                'message': result.get('message', 'Payment not completed'),
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's sales summary"""
        today = timezone.now().date()
        today_sales = Sale.objects.filter(created_at__date=today)
        
        total_sales = today_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        total_transactions = today_sales.count()
        
        cash_sales = today_sales.filter(payment_method='cash').aggregate(total=Sum('total_amount'))['total'] or 0
        card_sales = today_sales.filter(payment_method='card').aggregate(total=Sum('total_amount'))['total'] or 0
        korapay_sales = today_sales.filter(payment_method='korapay').aggregate(total=Sum('total_amount'))['total'] or 0
        
        return Response({
            'summary': {
                'total_sales': float(total_sales),
                'count': total_transactions
            },
            'cash_sales': float(cash_sales),
            'card_sales': float(card_sales),
            'korapay_sales': float(korapay_sales),
            'transactions': SaleSerializer(today_sales, many=True).data
        })
    
    @action(detail=False, methods=['get'])
    def revenue_report(self, request):
        """Get revenue report by period"""
        period = request.query_params.get('period', 'weekly')
        
        today = timezone.now().date()
        
        if period == 'weekly':
            report = []
            for i in range(7):
                day = today - timedelta(days=6-i)
                day_sales = Sale.objects.filter(created_at__date=day)
                report.append({
                    'name': day.strftime('%a'),
                    'date': day.isoformat(),
                    'revenue': float(day_sales.aggregate(total=Sum('total_amount'))['total'] or 0),
                    'transactions': day_sales.count()
                })
        else:  # monthly
            report = []
            for i in range(4):
                week_start = today - timedelta(days=28-(i*7))
                week_end = week_start + timedelta(days=6)
                week_sales = Sale.objects.filter(created_at__date__gte=week_start, created_at__date__lte=week_end)
                report.append({
                    'name': f'Week {i+1}',
                    'revenue': float(week_sales.aggregate(total=Sum('total_amount'))['total'] or 0),
                    'transactions': week_sales.count()
                })
        
        return Response(report)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get sales statistics"""
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Today's stats
        today_sales = Sale.objects.filter(created_at__date=today)
        today_total = today_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        today_count = today_sales.count()
        
        # Weekly stats
        week_sales = Sale.objects.filter(created_at__date__gte=week_ago)
        week_total = week_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Monthly stats
        month_sales = Sale.objects.filter(created_at__date__gte=month_ago)
        month_total = month_sales.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Average order value
        avg_order = Sale.objects.aggregate(avg=Sum('total_amount') / Count('id'))['avg'] or 0
        
        return Response({
            'today': {
                'total': float(today_total),
                'count': today_count,
                'average': float(today_total / today_count) if today_count > 0 else 0,
            },
            'week': {
                'total': float(week_total),
                'count': week_sales.count(),
            },
            'month': {
                'total': float(month_total),
                'count': month_sales.count(),
            },
            'overall': {
                'average_order_value': float(avg_order),
                'total_sales': Sale.objects.count(),
                'total_revenue': float(Sale.objects.aggregate(total=Sum('total_amount'))['total'] or 0),
            }
        })

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by('-created_at')
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Customer.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )
        return queryset
    
    @action(detail=True, methods=['post'])
    def add_visit(self, request, pk=None):
        customer = self.get_object()
        customer.total_visits += 1
        customer.last_visit = timezone.now()
        customer.save()
        
        total_spent = Sale.objects.filter(customer=customer).aggregate(total=Sum('total_amount'))['total'] or 0
        customer.total_spent = total_spent
        customer.save()
        
        return Response(CustomerSerializer(customer).data)
    
    @action(detail=True, methods=['get'])
    def sales_history(self, request, pk=None):
        customer = self.get_object()
        sales = Sale.objects.filter(customer=customer).order_by('-created_at')
        return Response(SaleSerializer(sales, many=True).data)

class SavedCartViewSet(viewsets.ModelViewSet):
    queryset = SavedCart.objects.filter(is_completed=False).order_by('-created_at')
    serializer_class = SavedCartSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateSavedCartSerializer
        return SavedCartSerializer
    
    def get_queryset(self):
        queryset = SavedCart.objects.filter(is_completed=False)
        customer_id = self.request.query_params.get('customer')
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        return queryset
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        cart = self.get_object()
        cart.is_completed = True
        cart.completed_at = timezone.now()
        cart.save()
        return Response({'status': 'cart completed', 'cart_id': cart.id})