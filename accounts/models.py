from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class User(AbstractUser):
    ROLE_CHOICES = (
        ('CEO', 'CEO'),
        ('MANAGER', 'Manager'),
        ('RECEPTIONIST', 'Receptionist'),
        ('BAR_STAFF', 'Bar Staff'),
        ('HOUSEKEEPING', 'Housekeeping'),
        ('ADMIN', 'Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='RECEPTIONIST')
    phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.username

class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    
    def is_valid(self):
        from django.utils import timezone
        return not self.used and self.expires_at > timezone.now()
    
    def __str__(self):
        return f"Reset token for {self.email}"