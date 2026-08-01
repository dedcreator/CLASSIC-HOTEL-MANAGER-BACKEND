from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import uuid

User = get_user_model()

class Payment(models.Model):
    """Unified payment model for all transactions"""
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD = [
        ('korapay', 'Korapay'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Bank Transfer'),
    ]
    
    PAYMENT_TYPE = [
        ('sale', 'Bar Sale'),
        ('booking', 'Booking Payment'),
        ('checkin', 'Check-in Payment'),
        ('deposit', 'Deposit'),
        ('partial', 'Partial Payment'),
        ('full', 'Full Payment'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=100, unique=True, db_index=True)
    korapay_reference = models.CharField(max_length=100, blank=True, null=True)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, default='korapay')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE, default='sale')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    
    # Related objects (polymorphic)
    sale = models.ForeignKey('sales.Sale', on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True)
    checkin = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='checkin_payments')
    
    # Customer information
    customer_name = models.CharField(max_length=200, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    
    # Payment metadata
    metadata = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Created by
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['korapay_reference']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.transaction_id} - {self.amount} {self.currency}"
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    @property
    def is_pending(self):
        return self.status in ['pending', 'processing']
    
    def mark_completed(self, korapay_reference=None):
        """Mark payment as completed"""
        self.status = 'completed'
        self.paid_at = timezone.now()
        if korapay_reference:
            self.korapay_reference = korapay_reference
        self.save()
        self._update_related_object()
    
    def mark_failed(self, error_message=None):
        """Mark payment as failed"""
        self.status = 'failed'
        if error_message:
            self.metadata['error'] = error_message
        self.save()
    
    def _update_related_object(self):
        """Update the related object's payment status"""
        if self.sale:
            self.sale.payment_status = 'paid'
            self.sale.payment_method = self.payment_method
            self.sale.save()
        
        if self.booking:
            self.booking.payment_status = 'paid'
            self.booking.payment_method = self.payment_method
            self.booking.amount_paid = self.amount
            self.booking.save()
        
        if self.checkin:
            self.checkin.payment_status = 'paid'
            self.checkin.payment_method = self.payment_method
            self.checkin.amount_paid = self.amount
            self.checkin.save()

class PaymentLog(models.Model):
    """Log all payment events for audit"""
    
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='logs')
    event_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class WebhookEvent(models.Model):
    """Store webhook events from Korapay"""
    
    EVENT_TYPES = [
        ('charge.success', 'Charge Success'),
        ('charge.failed', 'Charge Failed'),
        ('charge.pending', 'Charge Pending'),
        ('transfer.success', 'Transfer Success'),
        ('transfer.failed', 'Transfer Failed'),
        ('refund.success', 'Refund Success'),
        ('refund.failed', 'Refund Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    reference = models.CharField(max_length=100, db_index=True)
    data = models.JSONField()
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']