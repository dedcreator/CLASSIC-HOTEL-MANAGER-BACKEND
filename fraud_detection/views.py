import logging
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model

from .models import FraudScanReport, FraudAuditFlag, FraudAISettings
from .serializers import (
    FraudScanReportSerializer,
    FraudAuditFlagSerializer,
    FraudAISettingsSerializer
)
from .permissions import IsCEO
from .services import FraudDetectionPipeline

User = get_user_model()
logger = logging.getLogger(__name__)


class FraudScanTriggerView(APIView):
    """
    CEO-only endpoint to initiate a deep AI forensic fraud scan.
    """
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def get(self, request):
        """Retrieve the most recent scan report, or auto-run initial scan if empty."""
        report = FraudScanReport.objects.first()
        if not report:
            report = FraudDetectionPipeline.run_scan(request.user, days=30)
        serializer = FraudScanReportSerializer(report)
        return Response(serializer.data)

    def post(self, request):
        """Execute a fresh on-demand forensic audit scan."""
        days = int(request.data.get('timeframe_days', 30))
        specific_staff_id = request.data.get('staff_id', None)

        try:
            report = FraudDetectionPipeline.run_scan(
                scanned_by_user=request.user,
                days=days,
                specific_staff_id=specific_staff_id
            )
            serializer = FraudScanReportSerializer(report)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error executing AI fraud scan: {e}", exc_info=True)
            return Response(
                {"error": f"Failed to complete AI fraud scan: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FraudReportListView(APIView):
    """List historical scan reports."""
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def get(self, request):
        reports = FraudScanReport.objects.all()[:20]
        serializer = FraudScanReportSerializer(reports, many=True)
        return Response(serializer.data)


class FraudReportDetailView(APIView):
    """Retrieve full details of a specific scan report."""
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def get(self, request, pk):
        report = get_object_or_404(FraudScanReport, pk=pk)
        serializer = FraudScanReportSerializer(report)
        return Response(serializer.data)


class FraudAuditFlagView(APIView):
    """Manage CEO flag status and notes for investigated staff members."""
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def get(self, request):
        flags = FraudAuditFlag.objects.all()
        serializer = FraudAuditFlagSerializer(flags, many=True)
        return Response(serializer.data)

    def post(self, request):
        staff_id = request.data.get('staff_id')
        new_status = request.data.get('status', 'under_investigation')
        notes = request.data.get('notes', '')
        action_plan = request.data.get('action_plan', '')
        risk_level = request.data.get('risk_level', 'HIGH')
        suspected_schemes = request.data.get('suspected_schemes', [])

        staff = get_object_or_404(User, id=staff_id)

        flag, created = FraudAuditFlag.objects.update_or_create(
            staff=staff,
            defaults={
                'status': new_status,
                'notes': notes,
                'action_plan': action_plan,
                'risk_level': risk_level,
                'suspected_schemes': suspected_schemes,
                'updated_by': request.user
            }
        )
        serializer = FraudAuditFlagSerializer(flag)
        return Response(serializer.data, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)


class FraudAISettingsView(APIView):
    """Configure AI engine and credentials for fraud detection."""
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def get(self, request):
        settings_obj = FraudAISettings.get_settings()
        serializer = FraudAISettingsSerializer(settings_obj)
        return Response(serializer.data)

    def post(self, request):
        settings_obj = FraudAISettings.get_settings()
        provider = request.data.get('provider')
        api_key = request.data.get('api_key')
        model_name = request.data.get('model_name')
        sensitivity = request.data.get('sensitivity')

        if provider:
            settings_obj.provider = provider
        if api_key is not None:
            settings_obj.api_key = api_key.strip()
        if model_name:
            settings_obj.model_name = model_name.strip()
        if sensitivity:
            settings_obj.sensitivity = sensitivity

        settings_obj.save()
        serializer = FraudAISettingsSerializer(settings_obj)
        return Response(serializer.data)


class TestAIConnectionView(APIView):
    """Verify connectivity with the selected AI provider."""
    permission_classes = [permissions.IsAuthenticated, IsCEO]

    def post(self, request):
        provider = request.data.get('provider', 'groq')
        api_key = request.data.get('api_key', '').strip()

        if not api_key:
            settings_obj = FraudAISettings.get_settings()
            api_key = settings_obj.api_key

        if not api_key:
            return Response({
                "status": "warning",
                "message": "No external API key provided. System will use internal High-Accuracy Forensic Engine."
            })

        try:
            if provider == 'groq':
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=8)
                if resp.status_code == 200:
                    return Response({"status": "success", "message": "Groq AI connection verified successfully! (LLaMA 3.3/3.1 ready)"})
                else:
                    return Response({
                        "status": "error",
                        "message": f"Groq responded with code {resp.status_code}: {resp.text}"
                    }, status=status.HTTP_400_BAD_REQUEST)

            elif provider == 'gemini':
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": "ping"}]}]}
                resp = requests.post(url, json=payload, timeout=8)
                if resp.status_code == 200:
                    return Response({"status": "success", "message": "Google Gemini connection verified successfully!"})
                else:
                    return Response({
                        "status": "error",
                        "message": f"Gemini responded with code {resp.status_code}: {resp.text}"
                    }, status=status.HTTP_400_BAD_REQUEST)

            return Response({"status": "success", "message": f"{provider} test request completed."})
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Connection test failed: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)
