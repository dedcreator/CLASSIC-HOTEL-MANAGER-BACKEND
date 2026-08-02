# backend/menu/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid
from decimal import Decimal

User = get_user_model()

class Category(models.Model):
    """Product categories like Starters, Main Course, Desserts, etc."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.CharField(max_length=50, blank=True, null=True, help_text="Icon name from Heroicons")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_categories')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

class MenuItem(models.Model):
    """Individual menu items with pricing and availability"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    
    # Dietary information
    is_vegetarian = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    
    # Status flags
    is_available = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    
    # Additional details
    preparation_time = models.IntegerField(default=15, help_text="Preparation time in minutes")
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    icon_name = models.CharField(max_length=50, blank=True, null=True, help_text="Icon name from Heroicons")
    
    # Sorting and metadata
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_menu_items')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'

    def __str__(self):
        return f"{self.name} - ₦{self.price}"

    @property
    def dietary_tags(self):
        """Return list of dietary tags"""
        tags = []
        if self.is_vegetarian:
            tags.append('Vegetarian')
        if self.is_vegan:
            tags.append('Vegan')
        if self.is_gluten_free:
            tags.append('Gluten-Free')
        return tags

class Order(models.Model):
    """Customer orders from the menu"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('served', 'Served'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True)
    
    # Foreign key to tables app - we'll use a string reference to avoid circular import
    table = models.ForeignKey('tables.Table', on_delete=models.CASCADE, related_name='orders')
    
    # Customer info (can be anonymous)
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Order details
    items = models.JSONField(default=list, help_text="List of ordered items with quantities")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, blank=True, null=True)
    
    # Timestamps
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Staff
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_orders')
    prepared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='prepared_orders')
    served_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='served_orders')
    
    # Additional
    notes = models.TextField(blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-placed_at']

    def __str__(self):
        return f"{self.order_number} - Table {self.table.table_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            import datetime
            year = datetime.date.today().year
            last_order = Order.objects.filter(
                order_number__startswith=f"ORD-{year}"
            ).order_by('-order_number').first()
            
            if last_order and last_order.order_number:
                last_num = int(last_order.order_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.order_number = f"ORD-{year}-{new_num:04d}"
        super().save(*args, **kwargs)

    def update_status(self, new_status, user=None):
        """Update order status with audit trail"""
        self.status = new_status
        
        if new_status == 'preparing' and user:
            self.prepared_by = user
            self.prepared_at = timezone.now()
        elif new_status == 'served' and user:
            self.served_by = user
            self.served_at = timezone.now()
        elif new_status == 'paid':
            self.paid_at = timezone.now()
        
        self.save()

class OrderItem(models.Model):
    """Individual items within an order (for detailed tracking)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, related_name='order_items')
    item_name = models.CharField(max_length=200)  # Snapshot of name at order time
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    special_instructions = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.item_name} x{self.quantity} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)