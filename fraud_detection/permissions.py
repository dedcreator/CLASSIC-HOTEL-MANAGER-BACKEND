from rest_framework import permissions

class IsCEO(permissions.BasePermission):
    """
    Strict permission check: Only accessible to CEO (case-insensitive).
    Any other staff role (Manager, Receptionist, Bar Staff, Housekeeping) receives 403 Forbidden.
    """
    message = "Access restricted: Confidential AI Fraud Detection is strictly accessible to the CEO only."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = (getattr(request.user, 'role', '') or '').upper()
        return role == 'CEO'
