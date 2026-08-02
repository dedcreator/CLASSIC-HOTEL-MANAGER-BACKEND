# backend/menu/permissions.py
from rest_framework import permissions

class IsManagerOrCEO(permissions.BasePermission):
    """
    Custom permission to only allow Managers and CEO to create/update/delete
    """
    def has_permission(self, request, view):
        # Allow read-only for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        
        # Allow write only for Managers and CEO
        return request.user and request.user.is_authenticated and (
            request.user.role in ['MANAGER', 'CEO']
        )

    def has_object_permission(self, request, view, obj):
        # Read permissions allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only for Managers and CEO
        return request.user.role in ['MANAGER', 'CEO']

class IsLoungeStaff(permissions.BasePermission):
    """
    Permission for lounge staff to update order status
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and (
            request.user.role in ['BAR_STAFF', 'MANAGER', 'CEO']
        )

class IsOwnerOrStaff(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Instance must have an attribute named `created_by` or `user`
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user or request.user.role in ['MANAGER', 'CEO']
        
        return request.user.role in ['MANAGER', 'CEO']