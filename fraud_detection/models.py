from django.db import models
from django.conf import settings
import uuid

class FraudScanReport(models.Model):
    """Stores full forensic fraud scan records generated for the CEO."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scanned_at = models.DateTimeField(auto_now_add=True)
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='fraud_scans'
    )
    timeframe_days = models.IntegerField(default=30)
    total_staff_analyzed = models.IntegerField(default=0)
    flagged_staff_count = models.IntegerField(default=0)
    high_risk_count = models.IntegerField(default=0)
    medium_risk_count = models.IntegerField(default=0)
    low_risk_count = models.IntegerField(default=0)
    total_potential_loss = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    ai_provider_used = models.CharField(max_length=50, default='groq')
    executive_summary = models.TextField(blank=True)
    analysis_results = models.JSONField(default=list)

    class Meta:
        ordering = ['-scanned_at']

    def __str__(self):
        return f"Fraud Scan {self.scanned_at.strftime('%Y-%m-%d %H:%M')} - Flagged: {self.flagged_staff_count}"


class FraudAuditFlag(models.Model):
    """CEO action log for investigated staff members."""
    STATUS_CHOICES = [
        ('under_investigation', 'Under Investigation'),
        ('cleared', 'Cleared / False Positive'),
        ('warning_issued', 'Written Warning Issued'),
        ('terminated', 'Suspended / Dismissed'),
        ('escalated', 'Escalated to Authorities'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fraud_flags'
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='under_investigation')
    risk_level = models.CharField(max_length=20, default='HIGH')
    suspected_schemes = models.JSONField(default=list)
    notes = models.TextField(blank=True)
    action_plan = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='updated_fraud_flags'
    )

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Flag: {self.staff.username} - {self.status}"


class FraudAISettings(models.Model):
    """Configuration for AI fraud analysis provider and credentials."""
    PROVIDER_CHOICES = [
        ('groq', 'Groq (Free LLaMA 3.3 70B)'),
        ('gemini', 'Google Gemini (Free Tier)'),
        ('xai', 'xAI Grok'),
        ('hybrid', 'Internal Forensic Engine'),
    ]

    SENSITIVITY_CHOICES = [
        ('low', 'Conservative'),
        ('medium', 'Balanced'),
        ('high', 'Strict / High Sensitivity'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default='groq')
    api_key = models.CharField(max_length=255, blank=True, default='')
    model_name = models.CharField(max_length=100, default='llama-3.3-70b-versatile')
    sensitivity = models.CharField(max_length=20, choices=SENSITIVITY_CHOICES, default='medium')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Fraud AI Settings'
        verbose_name_plural = 'Fraud AI Settings'

    @classmethod
    def get_settings(cls):
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create(
                provider='groq',
                model_name='llama-3.3-70b-versatile',
                sensitivity='medium'
            )
        return obj
