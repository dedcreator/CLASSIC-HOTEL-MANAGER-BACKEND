from rest_framework import views, status, permissions
from rest_framework.response import Response
from django.conf import settings
from django.db.models import Q
from .models import PushSubscription, Notification
from .serializers import PushSubscriptionSerializer, NotificationSerializer
from .services import send_push_async, send_push_notification


class VapidPublicKeyView(views.APIView):
    """Returns the application server public key for Web Push registration."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        public_key = getattr(
            settings,
            'VAPID_PUBLIC_KEY',
            'BD-AGsAC0qvm8GPm0w5DqVg3Gti8akIsqL2c0zNiP4Euk05UDbIrPt4cUwORZllPcR4bLfy5492eoANPOWMzH7o'
        )
        return Response({'publicKey': public_key})


class PushSubscribeView(views.APIView):
    """Registers or updates a Web Push subscription for the active user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data
        endpoint = data.get('endpoint')
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return Response(
                {'error': 'endpoint and keys (p256dh, auth) are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user_agent = request.META.get('HTTP_USER_AGENT', '')

        # Upsert subscription
        subscription, created = PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                'user': request.user,
                'p256dh': p256dh,
                'auth': auth,
                'user_agent': user_agent,
            }
        )

        return Response({
            'success': True,
            'created': created,
            'subscription_id': str(subscription.id)
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PushUnsubscribeView(views.APIView):
    """Removes a push subscription."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get('endpoint')
        if not endpoint:
            return Response({'error': 'endpoint is required'}, status=status.HTTP_400_BAD_REQUEST)

        PushSubscription.objects.filter(endpoint=endpoint).delete()
        return Response({'success': True, 'message': 'Unsubscribed successfully'})


class PushTestView(views.APIView):
    """Sends a test push notification to the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        send_push_notification(
            users=[request.user],
            title='Classic Hotel Test Push',
            body='Push notifications are active and working!',
            url='/',
            data={'type': 'test'}
        )
        return Response({'success': True, 'message': 'Test push sent'})


class NotificationListView(views.APIView):
    """List notifications relevant to the authenticated user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (user.role or '').upper()

        q = Q(user=user) | Q(role_target__iexact=role) | Q(role_target__iexact='ALL')
        notifications = Notification.objects.filter(q).order_by('-created_at')[:50]

        serializer = NotificationSerializer(notifications, many=True, context={'request': request})
        return Response(serializer.data)


class NotificationUnreadCountView(views.APIView):
    """Returns the unread notifications count for the authenticated user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (user.role or '').upper()

        # Direct unread
        direct_unread = Notification.objects.filter(user=user, is_read=False).count()

        # Role unread (exclude ones where user is in read_by)
        role_unread = Notification.objects.filter(
            Q(role_target__iexact=role) | Q(role_target__iexact='ALL')
        ).exclude(read_by=user).count()

        return Response({'unread_count': direct_unread + role_unread})


class NotificationMarkReadView(views.APIView):
    """Mark a single notification as read."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)

        if notification.user_id == request.user.id:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        else:
            notification.read_by.add(request.user)

        return Response({'success': True})


class NotificationMarkAllReadView(views.APIView):
    """Mark all relevant notifications as read for current user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        role = (user.role or '').upper()

        # Mark direct ones
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)

        # Add user to read_by for role ones
        role_notifications = Notification.objects.filter(
            Q(role_target__iexact=role) | Q(role_target__iexact='ALL')
        ).exclude(read_by=user)

        for n in role_notifications:
            n.read_by.add(user)

        return Response({'success': True})
