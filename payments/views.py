from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Payment, PaymentLog
from .serializers import PaymentSerializer, PaymentInitSerializer, PaymentVerifySerializer
from .services import korapay_service
from sales.models import Sale
from bookings.models import Booking
import logging

logger = logging.getLogger(__name__)

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by('-created_at')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        payment_type = self.request.query_params.get('payment_type')
        if payment_type:
            queryset = queryset.filter(payment_type=payment_type)
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    @action(detail=False, methods=['post'])
    def initialize(self, request):
        """Initialize a payment for sale or booking"""
        serializer = PaymentInitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        payment_type = data.get('payment_type')
        reference = data.get('reference') or korapay_service.generate_reference()
        
        with transaction.atomic():
            sale_id = data.get('sale_id')
            booking_id = data.get('booking_id')
            
            related_object = None
            total_amount = data.get('amount', 0)
            customer_name = data.get('customer_name', '')
            customer_email = data.get('customer_email', '')
            
            if sale_id:
                sale = get_object_or_404(Sale, id=sale_id)
                related_object = sale
                total_amount = sale.total_amount if not total_amount else total_amount
                customer_name = customer_name or sale.guest_name
            elif booking_id:
                booking = get_object_or_404(Booking, id=booking_id)
                related_object = booking
                total_amount = booking.total_amount if not total_amount else total_amount
                customer_name = customer_name or booking.guest.get_full_name()
                customer_email = customer_email or booking.guest.email
            
            if not total_amount:
                return Response({
                    'success': False,
                    'error': 'Amount is required',
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create payment record
            payment = Payment.objects.create(
                transaction_id=reference,
                amount=total_amount,
                payment_type=payment_type,
                status='pending',
                customer_name=customer_name or 'Guest',
                customer_email=customer_email,
                customer_phone=data.get('customer_phone', ''),
                sale=sale_id and related_object,
                booking=booking_id and related_object,
                description=data.get('description', ''),
                metadata=data.get('metadata', {}),
                created_by=request.user,
                expires_at=timezone.now() + timedelta(minutes=60),
            )
            
            # Initialize with Korapay
            callback_url = data.get('callback_url') or getattr(settings, 'KORAPAY_CALLBACK_URL', None)
            
            result = korapay_service.initialize_payment(
                amount=payment.amount,
                customer_email=payment.customer_email or request.user.email,
                customer_name=payment.customer_name,
                reference=reference,
                payment_type=payment_type,
                metadata={
                    'payment_id': str(payment.id),
                    'sale_id': sale_id,
                    'booking_id': booking_id,
                    **data.get('metadata', {})
                },
                callback_url=callback_url,
                description=data.get('description', ''),
            )
            
            if result.get('success'):
                payment.korapay_reference = result.get('payment_id', '')
                payment.save()
                
                return Response({
                    'success': True,
                    'payment_id': str(payment.id),
                    'reference': reference,
                    'payment_link': result.get('payment_link'),
                    'payment': PaymentSerializer(payment).data,
                }, status=status.HTTP_201_CREATED)
            else:
                payment.mark_failed(error_message=result.get('message'))
                
                return Response({
                    'success': False,
                    'message': result.get('message', 'Payment initialization failed'),
                    'payment_id': str(payment.id),
                }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def verify(self, request):
        """Verify a payment"""
        serializer = PaymentVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        reference = serializer.validated_data['reference']
        
        try:
            payment = Payment.objects.get(transaction_id=reference)
        except Payment.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Payment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        result = korapay_service.verify_payment(reference)
        
        if result.get('success'):
            if result.get('verified'):
                payment.mark_completed()
                return Response({
                    'success': True,
                    'verified': True,
                    'payment': PaymentSerializer(payment).data,
                })
            else:
                return Response({
                    'success': True,
                    'verified': False,
                    'message': 'Payment not completed yet',
                })
        else:
            return Response({
                'success': False,
                'message': result.get('message', 'Verification failed'),
            }, status=status.HTTP_400_BAD_REQUEST)