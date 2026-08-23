# backend/sales/models.py
from django.db import models
from django.db.models import Sum
from django.conf import settings
import uuid
from decimal import Decimal
from inventory.models import Product
from rooms.models import Room

class Sale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('transfer', 'Transfer'),
        ('korapay', 'Korapay'),
        ('bank_transfer', 'Bank Transfer'),
        ('room_charge', 'Room Charge'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_number = models.CharField(max_length=50, unique=True)
    guest_name = models.CharField(max_length=200, blank=True)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    payment_status = models.CharField(max_length=20, default='completed')
    notes = models.TextField(blank=True)
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='sales'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.transaction_number:
            import datetime
            today = datetime.date.today()
            year = today.strftime('%Y')
            month = today.strftime('%m')
            
            last_sale = Sale.objects.filter(
                transaction_number__startswith=f"POS-{year}{month}"
            ).order_by('-transaction_number').first()
            
            if last_sale:
                last_num = int(last_sale.transaction_number[-4:])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.transaction_number = f"POS-{year}{month}{new_num:04d}"
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.transaction_number} - ₦{self.total_amount}"

class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        # Calculate subtotal
        quantity = Decimal(str(self.quantity))
        unit_price = Decimal(str(self.unit_price))
        discount = Decimal(str(self.discount))
        self.subtotal = (quantity * unit_price) - discount
        
        # Save the item first
        super().save(*args, **kwargs)
        
        # Update sale totals
        sale = self.sale
        items = sale.items.all()
        
        # Recalculate sale totals
        subtotal = sum(Decimal(str(item.subtotal)) for item in items)
        sale.subtotal = subtotal
        sale.tax = (subtotal * Decimal('0.075')).quantize(Decimal('0.01'))
        sale.total_amount = (subtotal + sale.tax - Decimal(str(sale.discount))).quantize(Decimal('0.01'))
        sale.save()
        
        # Update product stock
        self.product.total_stock -= self.quantity
        self.product.save()
        
        # Record stock movement
        try:
            from inventory.models import StockMovement
            StockMovement.objects.create(
                product=self.product,
                quantity=-self.quantity,
                movement_type='sale',
                price_at_movement=self.unit_price,
                notes=f"Sale {self.sale.transaction_number}",
                created_by=self.sale.staff
            )
        except Exception as e:
            # Log but don't fail the sale
            print(f"Stock movement error: {e}")
    
    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_vip = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    total_visits = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_visit = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    class Meta:
        ordering = ['-created_at']

class SavedCart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='saved_carts')
    cart_data = models.JSONField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Cart for {self.customer} - ₦{self.total}"
    
    class Meta:
        ordering = ['-created_at']