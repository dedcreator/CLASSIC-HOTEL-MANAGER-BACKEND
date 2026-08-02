# backend/tables/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from django.utils.text import slugify
import uuid

User = get_user_model()

class Table(models.Model):
    """Dining tables with QR codes and management"""
    
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('reserved', 'Reserved'),
        ('cleaning', 'Cleaning'),
        ('maintenance', 'Maintenance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    table_number = models.CharField(max_length=10, unique=True, help_text="Display number (e.g., 1, 2, 3 or A1, B2)")
    name = models.CharField(max_length=100, help_text="Friendly name (e.g., Garden View, Window Seat)")
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="URL-friendly name (e.g., garden-view)")
    capacity = models.IntegerField(default=2, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    qr_code = models.TextField(blank=True, null=True, help_text="Base64 QR code image")
    is_active = models.BooleanField(default=True)
    
    # Location/Area
    section = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Indoor, Outdoor, VIP")
    floor = models.CharField(max_length=50, blank=True, null=True, help_text="e.g., Ground, First, Second")
    
    # Metadata - Use unique related_name to avoid conflicts
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_restaurant_tables')
    
    class Meta:
        ordering = ['table_number']
        verbose_name_plural = 'Tables'
    
    def __str__(self):
        return f"Table {self.table_number} - {self.name or 'No name'}"
    
    def save(self, *args, **kwargs):
        # Generate slug if not provided
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Table.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        super().save(*args, **kwargs)
    
    def generate_qr_code(self, base_url=None):
        """Generate QR code for this table"""
        try:
            import qrcode
            from io import BytesIO
            import base64
        except ImportError:
            return None
        
        if not base_url:
            from django.conf import settings
            base_url = getattr(settings, 'BASE_URL', 'https://yourdomain.com')
        
        # The URL will use the slug for better readability
        url = f"{base_url}/menu/{self.slug}"
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="#16302B", back_color="#FAF6EF")
        
        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    
    def get_absolute_url(self):
        """Get the URL for this table's menu"""
        from django.urls import reverse
        return reverse('menu:table_menu', kwargs={'slug': self.slug})