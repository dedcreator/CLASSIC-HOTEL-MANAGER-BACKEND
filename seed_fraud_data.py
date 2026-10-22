# backend/seed_fraud_data.py
import os
import sys
import django
from datetime import timedelta, date
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from django.utils import timezone
from accounts.models import User
from inventory.models import Product, StockMovement
from sales.models import Sale, SaleItem
from bookings.models import Guest, Booking
from rooms.models import Room, RoomAccessCode, SecurityAuditLog
from consumables.models import Expense, ExpenseCategory


def seed_fraud_scenarios():
    print("🔍 Seeding Realistic Zero-Trust & Cashless Fraud Telemetry Scenarios...")

    now = timezone.now()

    # 1. Staff Accounts
    emeka, _ = User.objects.get_or_create(
        username='barstaff',
        defaults={'first_name': 'Emeka', 'last_name': 'Okafor', 'role': 'BAR_STAFF', 'email': 'emeka@hotel.com'}
    )
    john, _ = User.objects.get_or_create(
        username='barstaff2',
        defaults={'first_name': 'John', 'last_name': 'Obi', 'role': 'BAR_STAFF', 'email': 'john@hotel.com'}
    )
    amina, _ = User.objects.get_or_create(
        username='reception',
        defaults={'first_name': 'Amina', 'last_name': 'Bello', 'role': 'RECEPTIONIST', 'email': 'amina@hotel.com'}
    )
    bayo, _ = User.objects.get_or_create(
        username='housekeeper',
        defaults={'first_name': 'Bayo', 'last_name': 'Balogun', 'role': 'HOUSEKEEPING', 'email': 'bayo@hotel.com'}
    )
    folake, _ = User.objects.get_or_create(
        username='manager',
        defaults={'first_name': 'Folake', 'last_name': 'Adeyemi', 'role': 'MANAGER', 'email': 'manager@hotel.com'}
    )

    # 2. Rooms
    room_101, _ = Room.objects.get_or_create(room_number='101', defaults={'room_type': 'deluxe', 'base_price': Decimal('30000.00'), 'status': 'occupied'})
    room_102, _ = Room.objects.get_or_create(room_number='102', defaults={'room_type': 'standard', 'base_price': Decimal('22500.00'), 'status': 'occupied'})
    room_103, _ = Room.objects.get_or_create(room_number='103', defaults={'room_type': 'suite', 'base_price': Decimal('45000.00'), 'status': 'available'})
    room_104, _ = Room.objects.get_or_create(room_number='104', defaults={'room_type': 'standard', 'base_price': Decimal('22500.00'), 'status': 'available'}) # Vacant room for ghost charge
    room_202, _ = Room.objects.get_or_create(room_number='202', defaults={'room_type': 'deluxe', 'base_price': Decimal('35000.00'), 'status': 'cleaning'})

    # 3. Products
    hennessy = Product.objects.filter(name__icontains='Hennessy').first()
    jameson = Product.objects.filter(name__icontains='Jameson').first()
    heineken = Product.objects.filter(name__icontains='Heineken').first()

    # -------------------------------------------------------------
    # Scenario 1: Emeka Okafor (Bar Staff)
    #   - Phantom Liquor Wastage (to balance unrecorded drink sales)
    #   - Zero-Tolerance Cashless Policy Breach (claiming physical cash)
    #   - Ghost Room Charge on vacant Room 104
    # -------------------------------------------------------------
    print("  • Seeding Bar Staff anomalies (Phantom wastage, Ghost room charge, Cash breach)...")
    if hennessy:
        StockMovement.objects.create(
            product=hennessy,
            quantity=-2,
            movement_type='wastage',
            price_at_movement=hennessy.default_price,
            notes='Dropped 2 bottles during VIP lounge shift - glass broken',
            created_by=emeka
        )
    if jameson:
        StockMovement.objects.create(
            product=jameson,
            quantity=-3,
            movement_type='adjustment',
            price_at_movement=jameson.default_price,
            notes='Inventory adjustment: Bottle seal defective / spillage write-off',
            created_by=emeka
        )

    # Cashless Violation: Emeka records cash transactions
    for i in range(4):
        sale = Sale.objects.create(
            guest_name=f'Walk-in Customer #{201+i}',
            payment_method='cash',
            payment_status='completed',
            total_amount=Decimal('18000.00'),
            amount_paid=Decimal('18000.00'),
            staff=emeka
        )
        if heineken:
            SaleItem.objects.create(
                sale=sale,
                product=heineken,
                quantity=6,
                unit_price=Decimal('1500.00'),
                subtotal=Decimal('9000.00')
            )

    # Ghost Room Charge: Emeka bills a ₦45,000 liquor order to Room 104 (which is VACANT!)
    ghost_sale = Sale.objects.create(
        transaction_number='POS-GHOST-104',
        guest_name='Ghost Room Guest',
        room=room_104, # Room 104 is VACANT!
        payment_method='room_charge',
        payment_status='completed',
        total_amount=Decimal('45000.00'),
        amount_paid=Decimal('45000.00'),
        notes='Room charge billed to Room 104 while room status is available',
        staff=emeka
    )
    if jameson:
        SaleItem.objects.create(
            sale=ghost_sale,
            product=jameson,
            quantity=2,
            unit_price=Decimal('18500.00'),
            subtotal=Decimal('37000.00')
        )

    # -------------------------------------------------------------
    # Scenario 2: Amina Bello (Receptionist)
    #   - Emergency 1-Hour Override Abuse (Ghost Stays without booking)
    #   - Unpaid Check-in Code Issuance (Payment Pending on Korapay)
    #   - Cashless Policy Breach at Front Desk
    # -------------------------------------------------------------
    print("  • Seeding Reception anomalies (Emergency key ghost stays, Unpaid check-in bypass)...")
    guest_tunde, _ = Guest.objects.get_or_create(
        email='tunde.bakare@example.com',
        defaults={'first_name': 'Tunde', 'last_name': 'Bakare', 'phone': '08099887766'}
    )

    # Unpaid check-in: Door code issued, payment still pending!
    booking_unpaid, _ = Booking.objects.get_or_create(
        booking_reference='BK-2026-UNPAID',
        defaults={
            'guest': guest_tunde,
            'room': room_101,
            'check_in': date.today(),
            'check_out': date.today() + timedelta(days=2),
            'total_nights': 2,
            'total_amount': Decimal('60000.00'),
            'amount_paid': Decimal('0.00'), # ₦0 paid!
            'status': 'checked_in',
            'payment_status': 'pending',
            'payment_method': 'korapay',
            'created_by': amina,
            'checked_in_at': now - timedelta(hours=8)
        }
    )

    # Check-in access code issued to unpaid guest
    RoomAccessCode.objects.get_or_create(
        code='CHK-101-8812',
        defaults={
            'code_type': 'checkin',
            'room': room_101,
            'booking': booking_unpaid,
            'status': 'active',
            'created_by': amina,
            'valid_from': now - timedelta(hours=8),
            'valid_until': now + timedelta(days=2),
            'reason': 'Guest checked in before Korapay verification'
        }
    )
    SecurityAuditLog.objects.create(
        actor=amina,
        actor_username=amina.username,
        actor_role=amina.role,
        action='CHECKIN_CODE_GENERATED',
        room=room_101,
        room_number='101',
        booking=booking_unpaid,
        access_code='CHK-101-8812',
        details='Check-in door code generated while Korapay payment is PENDING (₦60,000 uncollected).',
        ip_address='192.168.1.15'
    )

    # Ghost Stays: Two 1-Hour Emergency Override Keys generated late night without any booking
    SecurityAuditLog.objects.create(
        actor=amina,
        actor_username=amina.username,
        actor_role=amina.role,
        action='EMERGENCY_CODE_GENERATED',
        room=room_103,
        room_number='103',
        access_code='EMG-103-9921',
        details='Emergency 1-Hour Access Code created at 01:45 AM with NO booking reference in system.',
        ip_address='192.168.1.15'
    )
    SecurityAuditLog.objects.create(
        actor=amina,
        actor_username=amina.username,
        actor_role=amina.role,
        action='EMERGENCY_CODE_GENERATED',
        room=room_103,
        room_number='103',
        access_code='EMG-103-7712',
        details='Emergency 1-Hour Access Code created at 03:20 AM with NO booking reference in system.',
        ip_address='192.168.1.15'
    )

    # Cashless Violation: Cash lodging settlement
    Booking.objects.get_or_create(
        booking_reference='BK-2026-CASH',
        defaults={
            'guest': guest_tunde,
            'room': room_102,
            'check_in': date.today() - timedelta(days=1),
            'check_out': date.today() + timedelta(days=1),
            'total_nights': 2,
            'total_amount': Decimal('45000.00'),
            'amount_paid': Decimal('45000.00'),
            'status': 'checked_in',
            'payment_status': 'paid',
            'payment_method': 'cash', # Prohibited cash payment!
            'created_by': amina,
            'checked_in_at': now - timedelta(days=1)
        }
    )

    # -------------------------------------------------------------
    # Scenario 3: Bayo Balogun (Housekeeping)
    #   - Housekeeping Cleaning Lock Lingering (>14 hours in cleaning)
    #   - Arbitrage for unofficial day-use lodging
    # -------------------------------------------------------------
    print("  • Seeding Housekeeping anomalies (Cleaning key lingering lock)...")
    cleaning_code, _ = RoomAccessCode.objects.get_or_create(
        code='CLN-202-4411',
        defaults={
            'code_type': 'cleaning',
            'room': room_202,
            'status': 'active',
            'created_by': bayo,
            'approved_by': folake,
            'approved_at': now - timedelta(hours=14),
            'valid_from': now - timedelta(hours=14),
            'valid_until': now + timedelta(hours=10),
            'reason': 'Routine deep clean after guest checkout'
        }
    )
    SecurityAuditLog.objects.create(
        actor=bayo,
        actor_username=bayo.username,
        actor_role=bayo.role,
        action='CLEANING_CODE_REQUESTED',
        room=room_202,
        room_number='202',
        access_code='CLN-202-4411',
        details='Cleaning access code approved 14 hours ago. Room status remains locked in cleaning.',
        ip_address='192.168.1.32'
    )

    # -------------------------------------------------------------
    # Scenario 4: Folake Adeyemi (Manager)
    #   - Cashless Procurement Violations & Unreceipted Vouchers
    # -------------------------------------------------------------
    print("  • Seeding Management anomalies (Cashless procurement bypass)...")
    supplies_cat, _ = ExpenseCategory.objects.get_or_create(
        name='Operations & Supplies',
        defaults={'description': 'General supplies'}
    )
    Expense.objects.create(
        category=supplies_cat,
        description='Emergency generator fuel purchase top-up',
        amount=Decimal('45000.00'),
        payment_method='cash', # Cash violation
        expense_date=date.today(),
        receipt_number='',
        notes='Cash paid directly to fuel supplier truck without invoice',
        created_by=folake
    )
    Expense.objects.create(
        category=supplies_cat,
        description='VIP Lounge provision stock replenishment',
        amount=Decimal('22000.00'),
        payment_method='cash',
        expense_date=date.today() - timedelta(days=2),
        receipt_number='',
        notes='Local market purchase without formal receipt',
        created_by=folake
    )

    # -------------------------------------------------------------
    # Scenario 5: John Obi (Clean Bar Staff - 100% Cashless Compliant)
    # -------------------------------------------------------------
    print("  • Seeding clean baseline records for John Obi (100% Korapay/Card compliant)...")
    for i in range(10):
        Sale.objects.create(
            guest_name=f'Verified Guest #{300+i}',
            payment_method='korapay' if i % 2 == 0 else 'card',
            payment_status='completed',
            discount=Decimal('0.00'),
            total_amount=Decimal('12500.00'),
            amount_paid=Decimal('12500.00'),
            staff=john
        )

    print("✅ Zero-Trust & Cashless Fraud Telemetry successfully seeded!")


if __name__ == '__main__':
    seed_fraud_scenarios()
