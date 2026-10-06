import os
import json
import logging
import threading
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)
User = get_user_model()


def get_vapid_private_key_path():
    """Returns the absolute path to the VAPID private key file."""
    path = getattr(settings, 'VAPID_PRIVATE_KEY_PATH', None)
    if path and os.path.exists(path):
        return path
    fallback = os.path.join(settings.BASE_DIR, 'vapid_private_key.pem')
    if os.path.exists(fallback):
        return fallback
    return None


def get_vapid_claims():
    """Returns the claims dict required by VAPID."""
    admin_email = getattr(settings, 'VAPID_ADMIN_EMAIL', 'admin@tsghotel.com.ng')
    return {'sub': f'mailto:{admin_email}'}


def _deliver_push_to_subscription(sub, payload):
    """Deliver a single Web Push payload to a PushSubscription."""
    from .models import PushSubscription

    key_path = get_vapid_private_key_path()
    if not key_path:
        logger.warning("VAPID private key file not found. Push notifications will not be signed.")
        return False

    subscription_info = {
        'endpoint': sub.endpoint,
        'keys': {
            'p256dh': sub.p256dh,
            'auth': sub.auth,
        }
    }

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=key_path,
            vapid_claims=get_vapid_claims(),
            ttl=86400  # 24 hours
        )
        logger.info(f"Push notification delivered successfully to endpoint: {sub.endpoint[:40]}...")
        return True
    except WebPushException as e:
        status_code = e.response.status_code if e.response else None
        logger.warning(f"WebPushException (status {status_code}) for endpoint {sub.endpoint[:40]}: {e}")
        # If subscription expired or was unsubscribed (404 Not Found or 410 Gone), remove it
        if status_code in (404, 410):
            logger.info(f"Removing inactive push subscription {sub.id}")
            try:
                sub.delete()
            except Exception as del_err:
                logger.error(f"Error removing subscription: {del_err}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending push notification to {sub.endpoint[:40]}: {e}")
        return False


def send_push_async(subscriptions, payload):
    """Send push notifications in a background thread to prevent blocking HTTP requests."""
    def worker():
        for sub in subscriptions:
            _deliver_push_to_subscription(sub, payload)

    t = threading.Thread(target=worker, daemon=True)
    t.start()


def send_push_notification(users=None, roles=None, title="", body="", url="/", data=None):
    """
    Sends push notification to users or roles.
    users: list or QuerySet of User instances or IDs
    roles: list of role strings (e.g. ['HOUSEKEEPING', 'CEO', 'RECEPTIONIST'])
    """
    from .models import PushSubscription
    from django.db.models import Q

    q = Q()
    has_filter = False

    if users:
        q |= Q(user__in=users)
        has_filter = True

    if roles:
        # Case insensitive role matching
        role_q = Q()
        for r in roles:
            role_q |= Q(user__role__iexact=r)
        q |= role_q
        has_filter = True

    if not has_filter:
        subscriptions = list(PushSubscription.objects.all())
    else:
        subscriptions = list(PushSubscription.objects.filter(q))

    if not subscriptions:
        logger.info(f"No push subscriptions found for users={users}, roles={roles}")
        return

    payload = {
        'title': title,
        'body': body,
        'url': url,
        'data': data or {},
        'icon': '/icons/icon-192x192.png',
        'badge': '/icons/icon-72x72.png',
        'tag': f"classic-hotel-{data.get('type', 'general') if data else 'general'}",
    }

    send_push_async(subscriptions, payload)


def send_in_app_notification(user=None, role_target=None, title="", message="", notification_type="system", data=None, link=""):
    """Creates an In-App Notification entry in the database."""
    from .models import Notification
    try:
        notification = Notification.objects.create(
            user=user,
            role_target=role_target.upper() if role_target else None,
            title=title,
            message=message,
            notification_type=notification_type,
            data=data or {},
            link=link or '',
        )
        return notification
    except Exception as e:
        logger.error(f"Error creating in-app notification: {e}")
        return None


def send_email_async(subject, message, recipient_list, html_message=None):
    """Sends email asynchronously in a background thread."""
    def worker():
        try:
            valid_recipients = [r for r in recipient_list if r and '@' in r]
            if not valid_recipients:
                logger.info(f"No valid recipients for email subject: {subject}")
                return
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'Classic Hotel <noreply@tsghotel.com.ng>'),
                recipient_list=valid_recipients,
                html_message=html_message,
                fail_silently=False,
            )
            logger.info(f"Email sent successfully to {valid_recipients} with subject: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_list}: {e}")

    t = threading.Thread(target=worker, daemon=True)
    t.start()


# =========================================================================
# DOMAIN EVENT NOTIFIERS
# =========================================================================

def notify_room_checkout(room, booking=None):
    """
    Called when a room is checked out.
    - Housekeeping staff get a push notification from the PWA.
    - Housekeeping gets an in-app notification.
    """
    title = f"Room {room.room_number} Checked Out"
    room_type_name = dict(room.ROOM_TYPES).get(room.room_type, room.room_type.capitalize())
    body = f"Room {room.room_number} ({room_type_name}) has been checked out and needs cleaning."
    url = f"/rooms?status=cleaning"
    extra_data = {
        'type': 'room_checkout',
        'room_id': str(room.id),
        'room_number': room.room_number,
        'booking_id': str(booking.id) if booking else None,
        'booking_reference': booking.booking_reference if booking else None,
    }

    # 1. PWA Push Notification to Housekeeping and Managers
    send_push_notification(
        roles=['HOUSEKEEPING', 'MANAGER', 'ADMIN'],
        title=title,
        body=body,
        url=url,
        data=extra_data
    )

    # 2. In-App Notification targeted to HOUSEKEEPING
    send_in_app_notification(
        role_target='HOUSEKEEPING',
        title=title,
        message=f"Room {room.room_number} is ready for housekeeping. Guest checked out.",
        notification_type='room_checkout',
        data=extra_data,
        link=url
    )
    logger.info(f"Dispatched checkout notifications for Room {room.room_number}")


def notify_website_booking(booking):
    """
    Called when a new booking is created from the website.
    - Email notification sent to hotel management / reception.
    - Receptionist gets an in-app notification.
    - Receptionist gets a PWA push notification.
    """
    guest = booking.guest
    room = booking.room
    guest_name = guest.get_full_name() if guest else "Website Guest"
    guest_email = guest.email if guest else "N/A"
    guest_phone = guest.phone if guest else "N/A"
    room_number = room.room_number if room else "Pending"
    room_type = room.get_room_type_display() if hasattr(room, 'get_room_type_display') else (room.room_type if room else "Standard")

    title = f"New Website Booking: {guest_name}"
    body = f"Room {room_number} ({room_type}) booked by {guest_name} ({booking.check_in} to {booking.check_out}). Total: ₦{booking.total_amount:,.2f}"
    url = f"/bookings"
    extra_data = {
        'type': 'website_booking',
        'booking_id': str(booking.id),
        'booking_reference': booking.booking_reference,
        'room_number': room_number,
        'guest_name': guest_name,
        'check_in': str(booking.check_in),
        'check_out': str(booking.check_out),
        'total_amount': float(booking.total_amount),
    }

    # 1. Push notification to Receptionists and Managers
    send_push_notification(
        roles=['RECEPTIONIST', 'MANAGER', 'ADMIN'],
        title=title,
        body=body,
        url=url,
        data=extra_data
    )

    # 2. In-App notification to RECEPTIONIST
    send_in_app_notification(
        role_target='RECEPTIONIST',
        title=title,
        message=body,
        notification_type='website_booking',
        data=extra_data,
        link=url
    )

    # 3. Email notification to hotel management and receptionists
    receptionist_emails = list(
        User.objects.filter(
            role__in=['RECEPTIONIST', 'MANAGER', 'CEO'],
            is_active=True
        ).exclude(email='').values_list('email', flat=True)
    )
    hotel_email = getattr(settings, 'HOTEL_NOTIFICATION_EMAIL', 'reception@tsghotel.com.ng')
    recipient_list = list(set([hotel_email] + receptionist_emails))

    email_subject = f"🔔 New Website Booking Confirmation: {booking.booking_reference} - {guest_name}"
    email_text = f"""
New Website Booking Received!

Booking Reference: {booking.booking_reference}
Guest Name: {guest_name}
Email: {guest_email}
Phone: {guest_phone}

Room: {room_number} ({room_type})
Check-In Date: {booking.check_in}
Check-Out Date: {booking.check_out}
Nights: {booking.total_nights}
Total Amount: ₦{booking.total_amount:,.2f}
Payment Status: {booking.payment_status.upper()}
Special Requests: {booking.special_requests or 'None'}

Please log into the hotel management dashboard to review and manage this booking.
    """.strip()

    email_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2A2622; background-color: #FAF6EF; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #DDD5C4; overflow: hidden;">
          <div style="background-color: #16302B; color: #F7F1E4; padding: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 22px; color: #C9A468;">Classic Hotel</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px;">New Website Booking Received</p>
          </div>
          <div style="padding: 24px;">
            <div style="background-color: #F7F1E4; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px;">
              <span style="font-size: 13px; color: #8A8377; text-transform: uppercase;">Booking Reference</span>
              <h2 style="margin: 4px 0 0 0; color: #16302B; font-size: 20px;">{booking.booking_reference}</h2>
            </div>
            
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Guest:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{guest_name}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Email:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{guest_email}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Phone:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{guest_phone}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Room:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">Room {room_number} ({room_type})</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Stay Period:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{booking.check_in} to {booking.check_out} ({booking.total_nights} night{'s' if booking.total_nights > 1 else ''})</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Total Amount:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-size: 16px; font-weight: bold; color: #16302B;">₦{booking.total_amount:,.2f}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Special Requests:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{booking.special_requests or 'None'}</td>
              </tr>
            </table>

            <div style="text-align: center; margin-top: 24px;">
              <a href="{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/bookings" style="background-color: #16302B; color: #F7F1E4; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View in Dashboard</a>
            </div>
          </div>
        </div>
      </body>
    </html>
    """.strip()

    send_email_async(
        subject=email_subject,
        message=email_text,
        recipient_list=recipient_list,
        html_message=email_html
    )
    logger.info(f"Dispatched website booking notifications for {booking.booking_reference}")


def notify_stock_added(product, batch=None, user=None, quantity=0):
    """
    Called when new stock is added.
    - CEO gets a push notification.
    - CEO gets an email notification.
    """
    staff_name = user.get_full_name() if (user and hasattr(user, 'get_full_name') and user.get_full_name()) else (user.username if user else "Staff")
    cost_price = batch.cost_price if batch and batch.cost_price else "N/A"
    selling_price = batch.selling_price if batch and batch.selling_price else product.default_price
    supplier = batch.supplier if batch and batch.supplier else "N/A"
    batch_num = batch.batch_number if batch and batch.batch_number else "N/A"

    title = f"📦 New Stock Added: {product.name}"
    body = f"{quantity} {product.unit}(s) of {product.name} added by {staff_name}. Total stock now: {product.total_stock}."
    url = f"/inventory"
    extra_data = {
        'type': 'stock_added',
        'product_id': str(product.id),
        'product_name': product.name,
        'quantity': quantity,
        'total_stock': product.total_stock,
        'batch_id': str(batch.id) if batch else None,
        'added_by': staff_name,
    }

    # 1. PWA Push Notification to CEO
    send_push_notification(
        roles=['CEO'],
        title=title,
        body=body,
        url=url,
        data=extra_data
    )

    # 2. In-App Notification to CEO
    send_in_app_notification(
        role_target='CEO',
        title=title,
        message=body,
        notification_type='stock_added',
        data=extra_data,
        link=url
    )

    # 3. Email Notification to CEO users
    ceo_emails = list(
        User.objects.filter(
            role__iexact='CEO',
            is_active=True
        ).exclude(email='').values_list('email', flat=True)
    )

    if not ceo_emails:
        # Fallback to configured admin/hotel email if no CEO user has an email
        admin_email = getattr(settings, 'VAPID_ADMIN_EMAIL', 'ceo@tsghotel.com.ng')
        ceo_emails = [admin_email]

    email_subject = f"📦 Stock Alert: New Stock Added for {product.name}"
    email_text = f"""
Hello CEO,

New inventory stock has been received and added to the system.

Product: {product.name}
Category: {product.get_category_display() if hasattr(product, 'get_category_display') else product.category}
Quantity Added: {quantity} {product.unit}(s)
Current Total Stock: {product.total_stock} {product.unit}(s)
Selling Price: ₦{selling_price}
Cost Price: {f'₦{cost_price}' if cost_price != 'N/A' else 'Not specified'}
Supplier: {supplier}
Batch Number: {batch_num}
Received / Added By: {staff_name}

You can review inventory levels directly in the hotel dashboard.
    """.strip()

    email_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #2A2622; background-color: #FAF6EF; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #DDD5C4; overflow: hidden;">
          <div style="background-color: #16302B; color: #F7F1E4; padding: 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 22px; color: #C9A468;">Classic Hotel Inventory</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px;">Stock Receipt Notification</p>
          </div>
          <div style="padding: 24px;">
            <p style="font-size: 15px; margin-top: 0;">Hello <strong>CEO</strong>,</p>
            <p style="font-size: 14px; color: #5B564B;">New stock has been received and entered into the inventory system by <strong>{staff_name}</strong>.</p>
            
            <div style="background-color: #F7F1E4; padding: 16px; border-radius: 6px; margin: 16px 0;">
              <h3 style="margin: 0 0 8px 0; color: #16302B;">{product.name}</h3>
              <p style="margin: 0; font-size: 18px; font-weight: bold; color: #16302B;">
                +{quantity} {product.unit}(s)
                <span style="font-size: 13px; font-weight: normal; color: #8A8377; margin-left: 8px;">(Total in stock: {product.total_stock})</span>
              </p>
            </div>

            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold; width: 40%;">Category:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{product.category.capitalize()}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Selling Price:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">₦{selling_price}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Cost Price:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{f'₦{cost_price}' if cost_price != 'N/A' else 'Not specified'}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Supplier:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{supplier}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Batch Number:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{batch_num}</td>
              </tr>
              <tr>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4; font-weight: bold;">Received By:</td>
                <td style="padding: 8px 0; border-bottom: 1px solid #F7F1E4;">{staff_name}</td>
              </tr>
            </table>

            <div style="text-align: center; margin-top: 24px;">
              <a href="{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/inventory" style="background-color: #16302B; color: #F7F1E4; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View Inventory</a>
            </div>
          </div>
        </div>
      </body>
    </html>
    """.strip()

    send_email_async(
        subject=email_subject,
        message=email_text,
        recipient_list=ceo_emails,
        html_message=email_html
    )
    logger.info(f"Dispatched stock addition notifications to CEO for product {product.name}")
