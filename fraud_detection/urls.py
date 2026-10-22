from django.urls import path
from .views import (
    FraudScanTriggerView,
    FraudReportListView,
    FraudReportDetailView,
    FraudAuditFlagView,
    FraudAISettingsView,
    TestAIConnectionView
)

urlpatterns = [
    path('scan/', FraudScanTriggerView.as_view(), name='fraud-scan'),
    path('reports/', FraudReportListView.as_view(), name='fraud-reports-list'),
    path('reports/<uuid:pk>/', FraudReportDetailView.as_view(), name='fraud-report-detail'),
    path('flags/', FraudAuditFlagView.as_view(), name='fraud-flags'),
    path('settings/', FraudAISettingsView.as_view(), name='fraud-settings'),
    path('settings/test-connection/', TestAIConnectionView.as_view(), name='fraud-test-ai'),
]
