from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import FraudScanReport, FraudAuditFlag, FraudAISettings

User = get_user_model()

class FraudScanReportSerializer(serializers.ModelSerializer):
    scanned_by_username = serializers.CharField(source='scanned_by.username', read_only=True)

    class Meta:
        model = FraudScanReport
        fields = [
            'id', 'scanned_at', 'scanned_by_username', 'timeframe_days',
            'total_staff_analyzed', 'flagged_staff_count', 'high_risk_count',
            'medium_risk_count', 'low_risk_count', 'total_potential_loss',
            'ai_provider_used', 'executive_summary', 'analysis_results'
        ]


class FraudAuditFlagSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()
    staff_role = serializers.CharField(source='staff.role', read_only=True)
    staff_username = serializers.CharField(source='staff.username', read_only=True)

    class Meta:
        model = FraudAuditFlag
        fields = [
            'id', 'staff', 'staff_username', 'staff_name', 'staff_role',
            'status', 'risk_level', 'suspected_schemes', 'notes',
            'action_plan', 'created_at', 'updated_at'
        ]

    def get_staff_name(self, obj):
        return f"{obj.staff.first_name} {obj.staff.last_name}".strip() or obj.staff.username


class FraudAISettingsSerializer(serializers.ModelSerializer):
    # Mask API key for security when returning
    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = FraudAISettings
        fields = [
            'id', 'provider', 'api_key', 'api_key_masked',
            'model_name', 'sensitivity', 'updated_at'
        ]
        extra_kwargs = {
            'api_key': {'write_only': True, 'required': False, 'allow_blank': True}
        }

    def get_api_key_masked(self, obj):
        if not obj.api_key:
            return ""
        if len(obj.api_key) <= 8:
            return "••••••••"
        return f"{obj.api_key[:4]}••••••••{obj.api_key[-4:]}"
