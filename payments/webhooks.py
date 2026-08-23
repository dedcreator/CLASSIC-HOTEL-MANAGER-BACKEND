import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from .models import Payment, WebhookEvent, PaymentLog
from .services import korapay_service

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def korapay_webhook(request):
    """
    Handle webhook events from Korapay
    """
    try:
        # Get signature from headers
        signature = request.headers.get('x-korapay-signature')
        if not signature:
            logger.warning("No signature provided in webhook")
            return JsonResponse({'status': 'error', 'message': 'No signature'}, status=400)
        
        # Parse payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        
        # Verify signature
        if not korapay_service.verify_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)
        
        # Process the webhook
        with transaction.atomic():
            event_type = payload.get('event')
            reference = payload.get('reference')
            data = payload.get('data', {})
            
            # Check if already processed
            if WebhookEvent.objects.filter(reference=reference, event_type=event_type).exists():
                logger.info(f"Webhook {reference} - {event_type} already processed")
                return JsonResponse({'status': 'success', 'message': 'Already processed'})
            
            # Save webhook event
            webhook_event = WebhookEvent.objects.create(
                event_type=event_type,
                reference=reference,
                data=payload
            )
            
            # Process based on event type
            if event_type == 'charge.success':
                _handle_charge_success(payload, webhook_event)
            elif event_type == 'charge.failed':
                _handle_charge_failed(payload, webhook_event)
            elif event_type == 'charge.pending':
                _handle_charge_pending(payload, webhook_event)
            
            # Mark as processed
            webhook_event.processed = True
            webhook_event.processed_at = timezone.now()
            webhook_event.save()
            
        return JsonResponse({'status': 'success'}, status=200)
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def _handle_charge_success(payload, webhook_event):
    """Handle successful charge"""
    data = payload.get('data', {})
    reference = payload.get('reference')
    
    try:
        payment = Payment.objects.get(transaction_id=reference)
        payment.mark_completed(korapay_reference=data.get('id'))
        
        PaymentLog.objects.create(
            payment=payment,
            event_type='webhook.success',
            status='completed',
            data=payload
        )
        
        logger.info(f"Payment completed via webhook: {reference}")
        
    except Payment.DoesNotExist:
        logger.warning(f"Payment not found for reference: {reference}")
        # Could create payment record here if needed

def _handle_charge_failed(payload, webhook_event):
    """Handle failed charge"""
    data = payload.get('data', {})
    reference = payload.get('reference')
    
    try:
        payment = Payment.objects.get(transaction_id=reference)
        payment.mark_failed(error_message=data.get('message', 'Payment failed'))
        
        PaymentLog.objects.create(
            payment=payment,
            event_type='webhook.failed',
            status='failed',
            data=payload
        )
        
        logger.info(f"Payment failed via webhook: {reference}")
        
    except Payment.DoesNotExist:
        logger.warning(f"Payment not found for reference: {reference}")

def _handle_charge_pending(payload, webhook_event):
    """Handle pending charge"""
    reference = payload.get('reference')
    
    try:
        payment = Payment.objects.get(transaction_id=reference)
        payment.status = 'processing'
        payment.save()
        
        PaymentLog.objects.create(
            payment=payment,
            event_type='webhook.pending',
            status='processing',
            data=payload
        )
        
        logger.info(f"Payment pending via webhook: {reference}")
        
    except Payment.DoesNotExist:
        logger.warning(f"Payment not found for reference: {reference}")