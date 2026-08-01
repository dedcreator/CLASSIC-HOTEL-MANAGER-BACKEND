import hashlib
import hmac
import json
import requests
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.core.signing import TimestampSigner
from django.utils import timezone
from datetime import timedelta
import uuid

class KorapayService:
    """Service for interacting with Korapay API"""
    
    BASE_URL = "https://api.korapay.com"
    SANDBOX_URL = "https://api.korapay.com"
    
    def __init__(self):
        self.api_key = getattr(settings, 'KORAPAY_SECRET_KEY', '')
        self.public_key = getattr(settings, 'KORAPAY_PUBLIC_KEY', '')
        self.is_sandbox = getattr(settings, 'KORAPAY_SANDBOX', True)
        self.base_url = self.SANDBOX_URL if self.is_sandbox else self.BASE_URL
        self.signer = TimestampSigner()
        
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
    
    def initialize_payment(self, amount: Decimal, customer_email: str, 
                          customer_name: str = "", reference: str = None,
                          payment_type: str = "sale", 
                          metadata: dict = None,
                          callback_url: str = None,
                          description: str = ""):
        """
        Initialize a payment with Korapay
        
        Args:
            amount: Payment amount
            customer_email: Customer email
            customer_name: Customer name
            reference: Custom transaction reference
            payment_type: Type of payment (sale, booking, checkin)
            metadata: Additional metadata
            callback_url: Webhook callback URL
            description: Payment description
        
        Returns:
            dict: Response from Korapay with payment link
        """
        if not reference:
            reference = self.generate_reference()
        
        if not callback_url:
            callback_url = getattr(settings, 'KORAPAY_CALLBACK_URL', 
                                  'https://yourdomain.com/payments/verify')
        
        payload = {
            "amount": float(amount),
            "currency": "NGN",
            "reference": reference,
            "customer": {
                "email": customer_email,
                "name": customer_name,
            },
            "metadata": {
                "payment_type": payment_type,
                **(metadata or {})
            },
            "callback_url": callback_url,
            "description": description or f"{payment_type.capitalize()} payment",
            "expires_in": 60,  # Expires in 60 minutes
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/charges/initialize",
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                return {
                    'success': True,
                    'reference': reference,
                    'payment_link': data.get('data', {}).get('checkout_url'),
                    'payment_id': data.get('data', {}).get('id'),
                    'data': data.get('data', {})
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Payment initialization failed'),
                    'data': data
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
    
    def verify_payment(self, reference: str):
        """
        Verify a payment with Korapay
        
        Args:
            reference: Payment reference
        
        Returns:
            dict: Payment verification details
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/charges/verify/{reference}",
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                return {
                    'success': True,
                    'verified': data.get('data', {}).get('status') == 'completed',
                    'data': data.get('data', {})
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Verification failed'),
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
    
    def charge_card(self, amount: Decimal, card_token: str, email: str,
                   reference: str = None, metadata: dict = None):
        """
        Charge a customer's card directly (requires saved card token)
        """
        if not reference:
            reference = self.generate_reference()
        
        payload = {
            "amount": float(amount),
            "currency": "NGN",
            "reference": reference,
            "customer": {
                "email": email,
            },
            "card": {
                "token": card_token,
            },
            "metadata": metadata or {},
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/charges/charge",
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                return {
                    'success': True,
                    'reference': reference,
                    'data': data.get('data', {})
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Card charge failed'),
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
    
    def refund_payment(self, reference: str, amount: Decimal = None,
                      reason: str = "Customer refund"):
        """
        Refund a payment
        
        Args:
            reference: Original payment reference
            amount: Amount to refund (full if None)
            reason: Refund reason
        """
        payload = {
            "reference": reference,
            "reason": reason,
        }
        if amount is not None:
            payload["amount"] = float(amount)
        
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/refunds",
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status'):
                return {
                    'success': True,
                    'refund_id': data.get('data', {}).get('id'),
                    'data': data.get('data', {})
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Refund failed'),
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
    
    def generate_reference(self, prefix="PAY"):
        """Generate a unique transaction reference"""
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_part = str(uuid.uuid4())[:8].upper()
        return f"{prefix}{timestamp}{random_part}"
    
    def verify_webhook_signature(self, payload: dict, signature: str) -> bool:
        """
        Verify webhook signature from Korapay
        
        Args:
            payload: The webhook payload
            signature: The signature header
        
        Returns:
            bool: True if signature is valid
        """
        if not signature:
            return False
        
        secret = getattr(settings, 'KORAPAY_WEBHOOK_SECRET', '')
        if not secret:
            return False
        
        # If payload is dict, convert to string
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, sort_keys=True)
        else:
            payload_str = str(payload)
        
        # Create HMAC signature
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

# Singleton instance
korapay_service = KorapayService()