# backend/rooms/models.py
from django.db import models
import uuid

class Room(models.Model):
    ROOM_TYPES = (
        ('standard', 'Standard'),
        ('deluxe', 'Deluxe'),
        ('suite', 'Suite'),
        ('executive', 'Executive'),
        ('presidential', 'Presidential'),
    )
    
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Maintenance'),
        ('cleaning', 'Cleaning'),
        ('reserved', 'Reserved'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    description = models.TextField(blank=True)
    capacity = models.IntegerField(default=2)
    
    # New fields for front-facing website
    name = models.CharField(max_length=200, blank=True, null=True, help_text="Display name for the room")
    size = models.IntegerField(default=30, help_text="Room size in square meters")
    amenities = models.JSONField(default=list, blank=True, help_text="List of amenities")
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=4.8, help_text="Guest rating")
    review_count = models.IntegerField(default=0, help_text="Number of reviews")
    is_featured = models.BooleanField(default=False, help_text="Show on homepage")
    slug = models.SlugField(max_length=100, unique=True, blank=True, help_text="URL-friendly name")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.barcode:
            self.barcode = f"RM{self.room_number}"
        if not self.slug and self.name:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        elif not self.slug:
            self.slug = slugify(f"room-{self.room_number}")
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Room {self.room_number} - {self.room_type}"
    
    class Meta:
        ordering = ['room_number']