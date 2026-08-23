from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import json
import datetime
from .models import User, PasswordResetToken
from .serializers import (
    UserSerializer, CreateUserSerializer, UpdateUserSerializer,
    ForgotPasswordSerializer, VerifyResetTokenSerializer, ResetPasswordSerializer
)
from sales.models import Sale
from bookings.models import Booking
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

# ============= FUNCTION-BASED VIEWS =============

@csrf_exempt
def login(request):
    """Login view that returns both token and JWT"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username_or_email = data.get('username')
            password = data.get('password')
            
            if not username_or_email or not password:
                return JsonResponse({'error': 'Username and password required'}, status=400)
            
            username = username_or_email.strip()
            if '@' in username:
                try:
                    user_obj = User.objects.get(email__iexact=username)
                    username = user_obj.username
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    pass
            
            user = authenticate(username=username, password=password)
            
            if user is not None and user.is_active:
                django_login(request, user)
                
                # Create JWT tokens
                refresh = RefreshToken.for_user(user)
                
                # Get or create token for DRF Token Auth
                token, created = Token.objects.get_or_create(user=user)
                
                user_data = {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'full_name': user.get_full_name(),
                    'role': user.role.upper(),
                    'phone': user.phone,
                    'is_active': user.is_active,
                }
                
                return JsonResponse({
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'token': token.key,
                    'user': user_data
                })
            else:
                return JsonResponse({'error': 'Invalid credentials'}, status=400)
                
        except Exception as e:
            print(f"Login error: {str(e)}")
            return JsonResponse({'error': 'Server error'}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def logout(request):
    """Logout view"""
    if request.method == 'POST':
        try:
            # Delete token if using token auth
            if request.user.is_authenticated:
                # Use filter().delete() to avoid DoesNotExist error
                Token.objects.filter(user=request.user).delete()
            
            django_logout(request)
            return JsonResponse({'message': 'Logged out successfully'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def me(request):
    """Get current user info"""
    if request.method == 'GET':
        # Try JWT token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                user = User.objects.get(id=user_id)
                
                if not user.is_active:
                    return JsonResponse({'error': 'User is inactive'}, status=401)
                
                serializer = UserSerializer(user)
                return JsonResponse(serializer.data)
            except Exception as e:
                print(f"JWT validation error: {str(e)}")
                return JsonResponse({'error': 'Invalid or expired token'}, status=401)
        
        # Fallback to session auth
        if request.user.is_authenticated:
            serializer = UserSerializer(request.user)
            return JsonResponse(serializer.data)
        
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def register(request):
    """Register a new user"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            serializer = CreateUserSerializer(data=data)
            
            if serializer.is_valid():
                user = serializer.save()
                token, created = Token.objects.get_or_create(user=user)
                refresh = RefreshToken.for_user(user)
                
                return JsonResponse({
                    'token': token.key,
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': UserSerializer(user).data
                }, status=201)
            else:
                return JsonResponse({'errors': serializer.errors}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ============= PASSWORD RESET VIEWS =============

@csrf_exempt
def forgot_password(request):
    """Send password reset email"""
    if request.method == 'POST':
        try:
            # Parse JSON body
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON format'}, status=400)
            
            serializer = ForgotPasswordSerializer(data=data)
            
            if serializer.is_valid():
                email = serializer.validated_data['email']
                user = User.objects.get(email=email)
                
                # Delete old unused tokens for this user
                PasswordResetToken.objects.filter(user=user, used=False).delete()
                
                # Create new token (expires in 24 hours)
                token = PasswordResetToken.objects.create(
                    user=user,
                    email=email,
                    expires_at=timezone.now() + timedelta(hours=24)
                )
                
                # Build reset link
                reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token.token}"
                
                # Send email
                try:
                    email_subject = "Reset Your Hotel Manager Password"
                    email_message = f"""
Hello {user.get_full_name() or user.username},

You requested to reset your password for your Hotel Manager account.

Click the link below to reset your password:
{reset_link}

This link will expire in 24 hours.

If you didn't request this, please ignore this email.

Best regards,
Hotel Manager Team
"""
                    
                    send_mail(
                        email_subject,
                        email_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    
                    return JsonResponse({
                        "message": "Password reset link has been sent to your email",
                        "email": email
                    }, status=200)
                    
                except Exception as e:
                    print(f"Email sending failed: {e}")
                    return JsonResponse({
                        "error": "Failed to send email. Please try again later."
                    }, status=500)
            
            return JsonResponse(serializer.errors, status=400)
            
        except Exception as e:
            print(f"Forgot password error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def verify_reset_token(request):
    """Verify if reset token is valid"""
    if request.method == 'POST':
        try:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON format'}, status=400)
            
            serializer = VerifyResetTokenSerializer(data=data)
            
            if serializer.is_valid():
                token_uuid = serializer.validated_data['token']
                try:
                    token = PasswordResetToken.objects.get(token=token_uuid)
                    if token.is_valid():
                        return JsonResponse({
                            "valid": True,
                            "email": token.email,
                            "message": "Token is valid"
                        }, status=200)
                    else:
                        return JsonResponse({
                            "valid": False,
                            "message": "This reset link has expired"
                        }, status=400)
                except PasswordResetToken.DoesNotExist:
                    return JsonResponse({
                        "valid": False,
                        "message": "Invalid reset token"
                    }, status=400)
            
            return JsonResponse({
                "valid": False,
                "message": serializer.errors.get('token', ['Invalid token'])[0]
            }, status=400)
            
        except Exception as e:
            print(f"Verify token error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def reset_password(request):
    """Reset password using valid token"""
    if request.method == 'POST':
        try:
            try:
                data = json.loads(request.body)
                print(f"Reset password data received: {data}")
            except json.JSONDecodeError as e:
                return JsonResponse({'error': 'Invalid JSON format'}, status=400)
            
            # Manually validate passwords match first
            new_password = data.get('new_password')
            confirm_password = data.get('confirm_password')
            
            if not new_password or not confirm_password:
                return JsonResponse({'error': 'Both password fields are required'}, status=400)
            
            if new_password != confirm_password:
                return JsonResponse({'error': 'Passwords do not match'}, status=400)
            
            # Validate password strength
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            
            try:
                validate_password(new_password)
            except ValidationError as e:
                return JsonResponse({'error': ' '.join(e.messages)}, status=400)
            
            # Now validate with serializer
            serializer = ResetPasswordSerializer(data=data)
            
            if serializer.is_valid():
                token_uuid = serializer.validated_data['token']
                new_password = serializer.validated_data['new_password']
                
                try:
                    token = PasswordResetToken.objects.get(token=token_uuid)
                    
                    # Check token validity
                    if not token.is_valid():
                        return JsonResponse({
                            "error": "This reset link has expired"
                        }, status=400)
                    
                    # Reset password
                    user = token.user
                    user.set_password(new_password)
                    user.save()
                    
                    # Mark token as used
                    token.used = True
                    token.save()
                    
                    # Delete auth tokens to force re-login
                    Token.objects.filter(user=user).delete()
                    
                    return JsonResponse({
                        "message": "Password has been reset successfully. You can now login with your new password."
                    }, status=200)
                    
                except PasswordResetToken.DoesNotExist:
                    return JsonResponse({
                        "error": "Invalid reset token"
                    }, status=400)
            else:
                # Return the specific validation errors
                return JsonResponse(serializer.errors, status=400)
            
        except Exception as e:
            print(f"Reset password error: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# ============= VIEWSET FOR API ENDPOINTS =============

class StaffViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateUserSerializer
        elif self.action in ['update', 'partial_update']:
            return UpdateUserSerializer
        return UserSerializer
    
    def get_queryset(self):
        queryset = User.objects.all()
        
        # Filter by search term
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(phone__icontains=search)
            )
        
        # Filter by role
        role = self.request.query_params.get('role', None)
        if role:
            queryset = queryset.filter(role=role)
        
        # Filter by active status
        active = self.request.query_params.get('active', None)
        if active is not None:
            is_active = active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active)
        
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary statistics for all staff"""
        total = User.objects.count()
        active = User.objects.filter(is_active=True).count()
        inactive = User.objects.filter(is_active=False).count()
        
        # Count by role
        roles = User.objects.values('role').annotate(count=Count('id'))
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
            'roles': list(roles)
        })

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a staff member"""
        staff = self.get_object()
        staff.is_active = True
        staff.save()
        return Response({'status': 'activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a staff member"""
        staff = self.get_object()
        staff.is_active = False
        staff.save()
        return Response({'status': 'deactivated'})

    @action(detail=True, methods=['get'])
    def performance(self, request, pk=None):
        """Get staff performance metrics"""
        staff = self.get_object()
        days = int(request.query_params.get('days', 30))
        
        start_date = timezone.now() - timedelta(days=days)
        
        # Get sales data
        sales = Sale.objects.filter(
            staff=staff,
            created_at__gte=start_date
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount')
        )
        
        # Get bookings data
        bookings = Booking.objects.filter(
            created_by=staff,
            created_at__gte=start_date
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount')
        )
        
        # Get check-ins
        check_ins = Booking.objects.filter(
            created_by=staff,
            checked_in_at__isnull=False,
            created_at__gte=start_date
        ).count()
        
        return Response({
            'sales': {
                'count': sales['count'] or 0,
                'total': float(sales['total'] or 0)
            },
            'bookings': {
                'count': bookings['count'] or 0,
                'total': float(bookings['total'] or 0)
            },
            'check_ins': check_ins
        })

    @action(detail=True, methods=['get'])
    def sales(self, request, pk=None):
        """Get all sales transactions for a staff member"""
        staff = self.get_object()
        
        # Get date filters
        days = request.query_params.get('days')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        sales_qs = Sale.objects.filter(staff=staff)
        
        # Apply date filters
        if start_date:
            sales_qs = sales_qs.filter(created_at__date__gte=start_date)
        if end_date:
            sales_qs = sales_qs.filter(created_at__date__lte=end_date)
        if days and not (start_date or end_date):
            date_threshold = timezone.now() - timedelta(days=int(days))
            sales_qs = sales_qs.filter(created_at__gte=date_threshold)
        
        sales_qs = sales_qs.prefetch_related('items__product').order_by('-created_at')
        
        # Serialize data
        data = []
        for sale in sales_qs:
            sale_data = {
                'id': str(sale.id),
                'transaction_number': sale.transaction_number,
                'guest_name': sale.guest_name,
                'total_amount': float(sale.total_amount),
                'subtotal': float(sale.subtotal),
                'tax': float(sale.tax),
                'discount': float(sale.discount),
                'payment_method': sale.payment_method,
                'payment_status': sale.payment_status,
                'created_at': sale.created_at.isoformat(),
                'items': []
            }
            
            for item in sale.items.all():
                sale_data['items'].append({
                    'id': str(item.id),
                    'product': {
                        'id': str(item.product.id),
                        'name': item.product.name,
                    },
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'subtotal': float(item.subtotal)
                })
            
            data.append(sale_data)
        
        return Response(data)

    @action(detail=True, methods=['get'])
    def bookings(self, request, pk=None):
        """Get all bookings created by a staff member"""
        staff = self.get_object()
        
        # Get date filters
        days = request.query_params.get('days')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        bookings_qs = Booking.objects.filter(created_by=staff)
        
        # Apply date filters
        if start_date:
            bookings_qs = bookings_qs.filter(created_at__date__gte=start_date)
        if end_date:
            bookings_qs = bookings_qs.filter(created_at__date__lte=end_date)
        if days and not (start_date or end_date):
            date_threshold = timezone.now() - timedelta(days=int(days))
            bookings_qs = bookings_qs.filter(created_at__gte=date_threshold)
        
        bookings_qs = bookings_qs.select_related('guest', 'room').order_by('-created_at')
        
        # Serialize data
        data = []
        for booking in bookings_qs:
            data.append({
                'id': str(booking.id),
                'booking_reference': booking.booking_reference,
                'guest': {
                    'id': str(booking.guest.id),
                    'first_name': booking.guest.first_name,
                    'last_name': booking.guest.last_name,
                    'email': booking.guest.email,
                    'phone': booking.guest.phone,
                },
                'room': {
                    'id': str(booking.room.id),
                    'room_number': booking.room.room_number,
                    'room_type': booking.room.room_type,
                } if booking.room else None,
                'check_in': booking.check_in.isoformat(),
                'check_out': booking.check_out.isoformat(),
                'adults': booking.adults,
                'children': booking.children,
                'total_nights': booking.total_nights,
                'total_amount': float(booking.total_amount),
                'amount_paid': float(booking.amount_paid),
                'status': booking.status,
                'payment_status': booking.payment_status,
                'payment_method': booking.payment_method,
                'checked_in_at': booking.checked_in_at.isoformat() if booking.checked_in_at else None,
                'checked_out_at': booking.checked_out_at.isoformat() if booking.checked_out_at else None,
                'created_at': booking.created_at.isoformat(),
            })
        
        return Response(data)

    @action(detail=True, methods=['get'])
    def detailed_summary(self, request, pk=None):
        """Get comprehensive summary for a staff member"""
        staff = self.get_object()
        days = int(request.query_params.get('days', 30))
        date_threshold = timezone.now() - timedelta(days=days)
        
        # Sales summary
        sales = Sale.objects.filter(
            staff=staff,
            created_at__gte=date_threshold
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount'),
            cash=Sum('total_amount', filter=Q(payment_method='cash')),
            card=Sum('total_amount', filter=Q(payment_method='card')),
            transfer=Sum('total_amount', filter=Q(payment_method='transfer')),
            room_charge=Sum('total_amount', filter=Q(payment_method='room_charge')),
        )
        
        # Bookings summary
        bookings = Booking.objects.filter(
            created_by=staff,
            created_at__gte=date_threshold
        ).aggregate(
            count=Count('id'),
            total=Sum('total_amount'),
            confirmed=Count('id', filter=Q(status='confirmed')),
            checked_in=Count('id', filter=Q(status='checked_in')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )
        
        # Check-ins
        check_ins = Booking.objects.filter(
            created_by=staff,
            checked_in_at__gte=date_threshold
        ).count()
        
        # Daily breakdown (last 7 days)
        daily_sales = []
        for i in range(7):
            day = timezone.now().date() - timedelta(days=i)
            day_start = timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))
            day_end = timezone.make_aware(datetime.datetime.combine(day, datetime.time.max))
            
            day_sales = Sale.objects.filter(
                staff=staff,
                created_at__range=[day_start, day_end]
            ).aggregate(
                count=Count('id'),
                total=Sum('total_amount')
            )
            
            day_bookings = Booking.objects.filter(
                created_by=staff,
                created_at__range=[day_start, day_end]
            ).count()
            
            daily_sales.append({
                'date': day.isoformat(),
                'sales_count': day_sales['count'] or 0,
                'sales_total': float(day_sales['total'] or 0),
                'bookings_count': day_bookings
            })
        
        return Response({
            'staff': {
                'id': staff.id,
                'name': staff.get_full_name(),
                'username': staff.username,
                'role': staff.role,
                'email': staff.email,
                'phone': staff.phone,
                'is_active': staff.is_active,
                'joined': staff.created_at.isoformat()
            },
            'period': {
                'days': days,
                'start': date_threshold.isoformat(),
                'end': timezone.now().isoformat()
            },
            'sales': {
                'count': sales['count'] or 0,
                'total': float(sales['total'] or 0),
                'by_method': {
                    'cash': float(sales['cash'] or 0),
                    'card': float(sales['card'] or 0),
                    'transfer': float(sales['transfer'] or 0),
                    'room_charge': float(sales['room_charge'] or 0),
                }
            },
            'bookings': {
                'count': bookings['count'] or 0,
                'total': float(bookings['total'] or 0),
                'confirmed': bookings['confirmed'] or 0,
                'checked_in': bookings['checked_in'] or 0,
                'cancelled': bookings['cancelled'] or 0,
            },
            'check_ins': check_ins,
            'daily_breakdown': daily_sales
        })

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        """Export all staff data for CSV download"""
        staff = self.get_object()
        days = int(request.query_params.get('days', 30))
        date_threshold = timezone.now() - timedelta(days=days)
        
        # Get all sales and bookings
        sales = Sale.objects.filter(
            staff=staff,
            created_at__gte=date_threshold
        ).order_by('-created_at')
        
        bookings = Booking.objects.filter(
            created_by=staff,
            created_at__gte=date_threshold
        ).order_by('-created_at')
        
        # Prepare CSV data
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{staff.username}_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Date', 'Type', 'Reference', 'Amount', 'Payment Method', 'Details'])
        
        for sale in sales:
            writer.writerow([
                sale.created_at.strftime('%Y-%m-%d %H:%M'),
                'Sale',
                sale.transaction_number,
                float(sale.total_amount),
                sale.payment_method,
                f"{sale.items.count()} items - {sale.guest_name or 'Walk-in'}"
            ])
        
        for booking in bookings:
            writer.writerow([
                booking.created_at.strftime('%Y-%m-%d %H:%M'),
                'Booking',
                booking.booking_reference,
                float(booking.total_amount),
                booking.payment_method or 'N/A',
                f"Room {booking.room.room_number if booking.room else 'N/A'} - {booking.guest.last_name}"
            ])
        
        return response
@csrf_exempt
def update_profile(request):
    """Update user profile with password verification for sensitive changes"""
    if request.method != 'PUT' and request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Check authentication via JWT token
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    # Get user from token (you need to verify the JWT token)
    # For now, use request.user if session auth is working
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    try:
        data = json.loads(request.body)
        user = request.user
        
        print(f"Updating profile for user: {user.username}")
        print(f"Update data: {data}")
        
        # Update basic info (no password needed)
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        
        # Sensitive changes require password verification
        email_changed = 'email' in data and data['email'] != user.email
        username_changed = 'username' in data and data['username'] != user.username
        
        if email_changed or username_changed:
            password = data.get('password')
            if not password:
                return JsonResponse({'error': 'Password required for email/username change'}, status=400)
            
            # Verify password
            from django.contrib.auth import authenticate
            auth_user = authenticate(username=user.username, password=password)
            if not auth_user:
                return JsonResponse({'error': 'Invalid password'}, status=401)
            
            if email_changed:
                # Check if email is already taken
                if User.objects.filter(email=data['email']).exclude(id=user.id).exists():
                    return JsonResponse({'error': 'Email already exists'}, status=400)
                user.email = data['email']
            
            if username_changed:
                # Check if username is already taken
                if User.objects.filter(username=data['username']).exclude(id=user.id).exists():
                    return JsonResponse({'error': 'Username already exists'}, status=400)
                user.username = data['username']
        
        user.save()
        
        return JsonResponse({
            'message': 'Profile updated successfully',
            'user': {
                'id': str(user.id),
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.role,
                'phone': user.phone,
            }
        }, status=200)
        
    except Exception as e:
        print(f"Update profile error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def change_password(request):
    """Change user password with current password verification"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Check authentication
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    try:
        data = json.loads(request.body)
        user = request.user
        
        print(f"Changing password for user: {user.username}")
        
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return JsonResponse({'error': 'Current password and new password required'}, status=400)
        
        # Verify current password
        from django.contrib.auth import authenticate
        if not authenticate(username=user.username, password=current_password):
            return JsonResponse({'error': 'Current password is incorrect'}, status=401)
        
        # Validate new password
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        
        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return JsonResponse({'error': ' '.join(e.messages)}, status=400)
        
        # Change password
        user.set_password(new_password)
        user.save()
        
        # Delete all auth tokens to force re-login
        from rest_framework.authtoken.models import Token
        Token.objects.filter(user=user).delete()
        
        return JsonResponse({'message': 'Password changed successfully. Please login again.'}, status=200)
        
    except Exception as e:
        print(f"Change password error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
    

class CustomTokenRefreshView(TokenRefreshView):
    """Custom token refresh view with better error handling"""
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        
        return Response(serializer.validated_data, status=status.HTTP_200_OK)