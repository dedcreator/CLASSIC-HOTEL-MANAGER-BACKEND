# backend/rooms/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
import secrets
import string

def generate_access_code(prefix="AC", length=6):
    digits = ''.join(secrets.choice(string.digits) for _ in range(length))
    return f"{prefix}-{digits}"

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
            from django.utils.text import slugify
            self.slug = slugify(f"room-{self.room_number}")
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Room {self.room_number} - {self.room_type}"
    
    class Meta:
        ordering = ['room_number']


class RoomAccessCode(models.Model):
    CODE_TYPES = (
        ('checkin', 'Check-in Guest Access'),
        ('emergency', 'Emergency Override (1 Hour)'),
        ('cleaning', 'Housekeeping Cleaning Access'),
    )
    
    STATUS_CHOICES = (
        ('pending_approval', 'Pending Manager Approval'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('used', 'Used / Completed'),
        ('revoked', 'Revoked'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    code_type = models.CharField(max_length=20, choices=CODE_TYPES)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='access_codes')
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='access_codes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_access_codes')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_access_codes')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({self.code_type} - {self.room.room_number})"

    @property
    def is_valid(self):
        if self.status != 'active':
            return False
        return timezone.now() <= self.valid_until


class SecurityAuditLog(models.Model):
    ACTION_CHOICES = (
        ('CHECKIN_CODE_GENERATED', 'Check-in Access Code Generated'),
        ('ACCESS_CODE_VERIFIED', 'Access Code Verified'),
        ('EMERGENCY_CODE_GENERATED', 'Emergency 1-Hour Code Generated'),
        ('CLEANING_CODE_REQUESTED', 'Cleaning Access Code Requested'),
        ('CLEANING_CODE_APPROVED', 'Cleaning Access Code Approved'),
        ('CLEANING_CODE_REJECTED', 'Cleaning Access Code Rejected'),
        ('ROOM_CLEANED_ACTIVATED', 'Room Cleaned & Activated to Available'),
        ('ROOM_STATUS_CHANGED', 'Room Status Changed'),
        ('ACCESS_CODE_REVOKED', 'Access Code Revoked'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='security_audit_logs')
    actor_username = models.CharField(max_length=150)
    actor_role = models.CharField(max_length=50)
    action = models.CharField(max_length=60, choices=ACTION_CHOICES, db_index=True)
    
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='security_audit_logs')
    room_number = models.CharField(max_length=20, blank=True)
    booking = models.ForeignKey('bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='security_audit_logs')
    booking_reference = models.CharField(max_length=50, blank=True)
    
    access_code = models.CharField(max_length=50, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.CharField(max_length=45, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.actor_username} ({self.actor_role}) - {self.action} on Room {self.room_number}"


def log_security_event(request=None, actor=None, action="", room=None, booking=None, access_code="", details=""):
    actor_obj = None
    actor_user = "system"
    actor_role = "SYSTEM"
    ip = None
    
    if request:
        if hasattr(request, 'user') and request.user.is_authenticated:
            actor_obj = request.user
            actor_user = request.user.username
            actor_role = getattr(request.user, 'role', 'STAFF')
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ip and ',' in ip:
            ip = ip.split(',')[0].strip()
    elif actor:
        actor_obj = actor
        actor_user = actor.username
        actor_role = getattr(actor, 'role', 'STAFF')
        
    r_num = room.room_number if room else (booking.room.room_number if booking and booking.room else '')
    b_ref = booking.booking_reference if booking else ''
    
    return SecurityAuditLog.objects.create(
        actor=actor_obj,
        actor_username=actor_user,
        actor_role=actor_role,
        action=action,
        room=room or (booking.room if booking else None),
        room_number=r_num,
        booking=booking,
        booking_reference=b_ref,
        access_code=access_code,
        details=details,
        ip_address=ip
    )