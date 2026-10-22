# backend/fraud_detection/services.py
import os
import json
import logging
from datetime import timedelta
from decimal import Decimal
import requests
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth import get_user_model

from sales.models import Sale, SaleItem
from inventory.models import StockMovement, Product
from bookings.models import Booking
from rooms.models import SecurityAuditLog, RoomAccessCode, Room
from consumables.models import Expense
from .models import FraudAISettings, FraudScanReport, FraudAuditFlag

User = get_user_model()
logger = logging.getLogger(__name__)


class StaffActivityCollector:
    """
    Collects operational telemetry for staff in a Zero-Trust, 100% Cashless Hotel environment:
    - Zero-Trust Door Security & Access Code Telemetry (Emergency keys, Cleaning keys, Audit logs)
    - Cashless Policy Compliance & Payment Gateway Reconciliation (Korapay bypass, Cash violations, Ghost room charges)
    - Inventory Shrinkage (Phantom wastage, Broken bottles, Spillage write-offs)
    - Consumables & Procurement Compliance
    """

    def __init__(self, days=30):
        self.days = days
        self.start_date = timezone.now() - timedelta(days=days)

    def get_staff_list(self):
        """Retrieve all active operational staff (excluding CEO)."""
        return User.objects.filter(
            is_active=True
        ).exclude(role='CEO').order_by('role', 'first_name')

    def collect_for_staff(self, staff_user):
        """Extract multi-dimensional telemetry tailored to Zero-Trust and Cashless operations."""
        # -------------------------------------------------------------
        # 1. Zero-Trust Access Key & Door Audit Telemetry
        # -------------------------------------------------------------
        audit_logs = SecurityAuditLog.objects.filter(
            actor=staff_user,
            timestamp__gte=self.start_date
        )

        emergency_codes_created = audit_logs.filter(action='EMERGENCY_CODE_GENERATED').count()
        emergency_off_hours = audit_logs.filter(
            action='EMERGENCY_CODE_GENERATED'
        ).filter(Q(timestamp__time__gte='23:00:00') | Q(timestamp__time__lte='05:00:00')).count()

        # Emergency codes without booking linkage
        emergency_without_booking = 0
        emergency_details = []
        for log in audit_logs.filter(action='EMERGENCY_CODE_GENERATED'):
            has_booking = bool(log.booking or log.booking_reference)
            if not has_booking:
                emergency_without_booking += 1
            emergency_details.append({
                'room': log.room_number,
                'access_code': log.access_code,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M'),
                'details': log.details,
                'has_booking': has_booking
            })

        # Cleaning key telemetry (Housekeeping & Managers)
        cleaning_requested = audit_logs.filter(action='CLEANING_CODE_REQUESTED').count()
        cleaning_approved = audit_logs.filter(action='CLEANING_CODE_APPROVED').count()

        # Check for lingering cleaning keys (rooms remaining in cleaning > 3 hours or unclosed keys)
        cleaning_codes_qs = RoomAccessCode.objects.filter(
            code_type='cleaning',
            created_at__gte=self.start_date
        ).filter(Q(created_by=staff_user) | Q(approved_by=staff_user))

        lingering_cleaning_count = 0
        cleaning_details = []
        for code in cleaning_codes_qs:
            # Check room status and elapsed duration
            room = code.room
            elapsed_hours = (timezone.now() - code.created_at).total_seconds() / 3600
            is_lingering = (room.status == 'cleaning' and elapsed_hours > 3) or (code.status == 'active' and elapsed_hours > 3)
            if is_lingering:
                lingering_cleaning_count += 1
                cleaning_details.append({
                    'room': room.room_number,
                    'code': code.code,
                    'status': code.status,
                    'room_status': room.status,
                    'elapsed_hours': round(elapsed_hours, 1),
                    'created_at': code.created_at.strftime('%Y-%m-%d %H:%M')
                })

        # Door verifications / denied entry attempts
        denied_door_verifications = audit_logs.filter(
            action='ACCESS_CODE_VERIFIED',
            details__icontains='Denied'
        ).count()

        # -------------------------------------------------------------
        # 2. Cashless Policy & Payment Gateway Reconciliation
        # -------------------------------------------------------------
        sales_qs = Sale.objects.filter(
            staff=staff_user,
            created_at__gte=self.start_date
        )
        total_sales_count = sales_qs.count()
        total_sales_revenue = float(sales_qs.aggregate(t=Sum('total_amount'))['t'] or 0)
        total_discount = float(sales_qs.aggregate(d=Sum('discount'))['d'] or 0)
        discount_count = sales_qs.filter(discount__gt=0).count()

        # ZERO-TOLERANCE CASH BREACHES (Platform is 100% Cashless)
        cash_sales_qs = sales_qs.filter(payment_method='cash')
        cash_sales_count = cash_sales_qs.count()
        cash_sales_amount = float(cash_sales_qs.aggregate(t=Sum('total_amount'))['t'] or 0)

        cash_sales_list = []
        for s in cash_sales_qs[:5]:
            cash_sales_list.append({
                'tx_number': s.transaction_number,
                'amount': float(s.total_amount),
                'guest': s.guest_name,
                'date': s.created_at.strftime('%Y-%m-%d %H:%M')
            })

        # Ghost Room Charges (Charging POS orders to rooms that are NOT currently occupied)
        room_charge_sales = sales_qs.filter(payment_method='room_charge')
        ghost_room_charges = []
        ghost_room_charge_amount = Decimal('0.00')

        for s in room_charge_sales:
            is_ghost = False
            reason = ""
            if not s.room:
                is_ghost = True
                reason = "No room attached to room_charge transaction"
            elif s.room.status != 'occupied':
                is_ghost = True
                reason = f"Room {s.room.room_number} was '{s.room.status}' (vacant/not occupied) at time of POS charge"
            else:
                # Check if there is an active checked-in booking for this room
                active_booking = Booking.objects.filter(
                    room=s.room,
                    status='checked_in'
                ).first()
                if not active_booking:
                    is_ghost = True
                    reason = f"No active checked-in booking on Room {s.room.room_number}"

            if is_ghost:
                ghost_room_charge_amount += s.total_amount
                ghost_room_charges.append({
                    'tx_number': s.transaction_number,
                    'room': s.room.room_number if s.room else 'None',
                    'amount': float(s.total_amount),
                    'guest': s.guest_name,
                    'reason': reason,
                    'date': s.created_at.strftime('%Y-%m-%d %H:%M')
                })

        # After-hours POS sales (11:00 PM to 05:00 AM)
        after_hours_sales = sales_qs.filter(
            Q(created_at__time__gte='23:00:00') | Q(created_at__time__lte='05:00:00')
        ).count()

        # -------------------------------------------------------------
        # 3. Reception & Booking Zero-Trust Telemetry
        # -------------------------------------------------------------
        bookings_created = Booking.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        total_bookings = bookings_created.count()

        # Zero-Tolerance Cash Bookings
        cash_bookings_qs = bookings_created.filter(payment_method='cash')
        cash_bookings_count = cash_bookings_qs.count()
        cash_bookings_amount = float(cash_bookings_qs.aggregate(t=Sum('total_amount'))['t'] or 0)

        # Unpaid / Pending Check-ins (Access Code issued without verified payment)
        unpaid_checkins_qs = bookings_created.filter(
            status='checked_in',
            payment_status__in=['pending', 'failed']
        )
        unpaid_checkins_count = unpaid_checkins_qs.count()
        unpaid_checkins_amount = float(sum((b.total_amount - b.amount_paid) for b in unpaid_checkins_qs))

        # Check-in cancellations (Booking cancelled AFTER check-in code was already generated)
        cancelled_after_checkin_qs = bookings_created.filter(
            status='cancelled',
            checked_in_at__isnull=False
        )
        cancelled_after_checkin_count = cancelled_after_checkin_qs.count()
        cancelled_after_checkin_amount = float(cancelled_after_checkin_qs.aggregate(t=Sum('total_amount'))['t'] or 0)

        suspicious_bookings_list = []
        for b in list(unpaid_checkins_qs[:5]) + list(cancelled_after_checkin_qs[:5]) + list(cash_bookings_qs[:5]):
            suspicious_bookings_list.append({
                'reference': b.booking_reference,
                'guest': str(b.guest),
                'room': b.room.room_number if b.room else 'N/A',
                'status': b.status,
                'payment_status': b.payment_status,
                'payment_method': b.payment_method,
                'total': float(b.total_amount),
                'paid': float(b.amount_paid),
                'date': b.created_at.strftime('%Y-%m-%d')
            })

        # -------------------------------------------------------------
        # 4. Inventory Shrinkage (Theft Disguised as Spillage/Wastage)
        # -------------------------------------------------------------
        movements_qs = StockMovement.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        wastage_qs = movements_qs.filter(movement_type='wastage')
        wastage_count = wastage_qs.count()
        wastage_units = abs(sum(m.quantity for m in wastage_qs))
        wastage_value = float(sum(abs(m.quantity) * float(m.price_at_movement) for m in wastage_qs))

        adjustment_qs = movements_qs.filter(movement_type='adjustment', quantity__lt=0)
        neg_adj_count = adjustment_qs.count()
        neg_adj_units = abs(sum(m.quantity for m in adjustment_qs))
        neg_adj_value = float(sum(abs(m.quantity) * float(m.price_at_movement) for m in adjustment_qs))
        total_shrinkage_value = wastage_value + neg_adj_value

        suspicious_stock_items = []
        for m in list(wastage_qs[:5]) + list(adjustment_qs[:5]):
            suspicious_stock_items.append({
                'type': m.get_movement_type_display(),
                'product': m.product.name,
                'quantity': abs(m.quantity),
                'cost': float(m.price_at_movement) * abs(m.quantity),
                'notes': m.notes or 'No reason provided',
                'date': m.created_at.strftime('%Y-%m-%d %H:%M')
            })

        # Wastage-to-sales ratio
        wastage_to_sales_ratio = (wastage_value / total_sales_revenue) if total_sales_revenue > 0 else (1.0 if wastage_value > 0 else 0.0)

        # -------------------------------------------------------------
        # 5. Consumables / Procurement Telemetry
        # -------------------------------------------------------------
        expenses_qs = Expense.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        total_expenses_count = expenses_qs.count()
        total_expense_amount = float(expenses_qs.aggregate(t=Sum('amount'))['t'] or 0)
        cash_expenses = expenses_qs.filter(payment_method='cash')
        cash_expense_amount = float(cash_expenses.aggregate(t=Sum('amount'))['t'] or 0)
        unreceipted_expenses = expenses_qs.filter(receipt_number='').count()

        return {
            'staff_id': str(staff_user.id),
            'username': staff_user.username,
            'full_name': f"{staff_user.first_name} {staff_user.last_name}".strip() or staff_user.username,
            'role': staff_user.role,
            'email': staff_user.email,
            'zero_trust': {
                'emergency_codes_created': emergency_codes_created,
                'emergency_off_hours': emergency_off_hours,
                'emergency_without_booking': emergency_without_booking,
                'emergency_details': emergency_details,
                'cleaning_requested': cleaning_requested,
                'cleaning_approved': cleaning_approved,
                'lingering_cleaning_count': lingering_cleaning_count,
                'cleaning_details': cleaning_details,
                'denied_door_verifications': denied_door_verifications,
            },
            'cashless_compliance': {
                'cash_sales_count': cash_sales_count,
                'cash_sales_amount': cash_sales_amount,
                'cash_sales_list': cash_sales_list,
                'cash_bookings_count': cash_bookings_count,
                'cash_bookings_amount': cash_bookings_amount,
                'total_cash_breaches': cash_sales_count + cash_bookings_count,
                'total_cash_amount': cash_sales_amount + cash_bookings_amount,
                'unpaid_checkins_count': unpaid_checkins_count,
                'unpaid_checkins_amount': unpaid_checkins_amount,
                'cancelled_after_checkin_count': cancelled_after_checkin_count,
                'cancelled_after_checkin_amount': cancelled_after_checkin_amount,
                'ghost_room_charges_count': len(ghost_room_charges),
                'ghost_room_charges_amount': float(ghost_room_charge_amount),
                'ghost_room_charges': ghost_room_charges,
                'suspicious_bookings': suspicious_bookings_list,
            },
            'inventory_shrinkage': {
                'wastage_count': wastage_count,
                'wastage_units': wastage_units,
                'wastage_value': wastage_value,
                'neg_adj_count': neg_adj_count,
                'neg_adj_units': neg_adj_units,
                'neg_adj_value': neg_adj_value,
                'total_shrinkage_value': round(total_shrinkage_value, 2),
                'wastage_to_sales_ratio': round(wastage_to_sales_ratio, 3),
                'suspicious_items': suspicious_stock_items,
                'total_discount': total_discount,
                'discount_count': discount_count,
                'after_hours_sales': after_hours_sales,
                'total_sales_count': total_sales_count,
                'total_sales_revenue': total_sales_revenue,
            },
            'procurement': {
                'total_expenses_count': total_expenses_count,
                'total_expense_amount': total_expense_amount,
                'cash_expense_amount': cash_expense_amount,
                'unreceipted_count': unreceipted_expenses,
            }
        }


class ForensicAnomalyDetector:
    """
    Evaluates staff activity strictly against Zero-Trust and Cashless Hospitality Rules:
    1. Zero-Trust Access Key Exploitation (Emergency overrides, Unpaired codes, Lingering cleaning locks)
    2. Cashless Gateway Evasion (Zero-tolerance physical cash, Unpaid check-in door codes, Cancelled stays)
    3. Ghost Room Charges at POS (Billing meals/drinks to vacant or cleaning rooms)
    4. Inventory Shrinkage (Theft disguised as spillage, breakage, or sample wastage)
    """

    @classmethod
    def evaluate(cls, telemetry):
        score = 0
        anomalies = []
        schemes = []
        evidence = []
        financial_exposure = Decimal('0.00')

        role = telemetry['role']
        zt = telemetry['zero_trust']
        cc = telemetry['cashless_compliance']
        inv = telemetry['inventory_shrinkage']
        proc = telemetry['procurement']

        # =============================================================
        # 1. ZERO-TRUST ACCESS CODE & DOOR SECURITY EVALUATION
        # =============================================================
        # A. Emergency 1-Hour Override Abuse (Ghost Stays / Unofficial Lodging)
        if zt['emergency_codes_created'] > 0:
            if zt['emergency_without_booking'] > 0:
                score += 35
                schemes.append("Zero-Trust Emergency Key Exploitation (Ghost Stays)")
                anomalies.append(
                    f"Generated {zt['emergency_without_booking']} emergency 1-hour access code(s) "
                    f"with NO active booking reference. High likelihood of unregistered guest occupancy."
                )
                # Financial exposure: estimated room rate (e.g. ₦30,000 per unlogged emergency stay)
                financial_exposure += Decimal(str(zt['emergency_without_booking'] * 30000))

            if zt['emergency_off_hours'] > 0:
                score += 20
                anomalies.append(
                    f"{zt['emergency_off_hours']} emergency access code(s) issued during off-hours (11:00 PM – 05:00 AM)."
                )

            for item in zt['emergency_details']:
                evidence.append({
                    'category': 'Zero-Trust Door Override',
                    'detail': f"Emergency Code {item['access_code']} on Room {item['room']} ({item['timestamp']})",
                    'date': item['timestamp'],
                    'notes': f"{item['details']} [Linked Booking: {'Yes' if item['has_booking'] else 'NONE - GHOST STAY RISK'}]"
                })

        # B. Housekeeping Key Hijacking & Lingering Cleaning Locks
        if zt['lingering_cleaning_count'] > 0:
            score += 25
            schemes.append("Housekeeping Cleaning Key Arbitrage (Day-Use Stays)")
            anomalies.append(
                f"{zt['lingering_cleaning_count']} room(s) maintained under active cleaning lock for >3 hours. "
                f"Creates opportunity for unrecorded short-rest / day-use rentals."
            )
            for item in zt['cleaning_details']:
                financial_exposure += Decimal('15000.00') # Typical short-rest rate
                evidence.append({
                    'category': 'Cleaning Lock Lingering',
                    'detail': f"Room {item['room']} held in cleaning status for {item['elapsed_hours']} hours (Code {item['code']})",
                    'date': item['created_at'],
                    'notes': f"Room status: {item['room_status']}. Key status: {item['status']}."
                })

        # C. Access Code Probing & Denied Entry Events
        if zt['denied_door_verifications'] >= 3:
            score += 15
            anomalies.append(
                f"{zt['denied_door_verifications']} denied / expired access code verification attempts logged on electronic door locks."
            )

        # =============================================================
        # 2. CASHLESS POLICY BREACHES & PAYMENT GATEWAY EVASION
        # =============================================================
        # A. Zero-Tolerance Physical Cash Handling (Strict Cashless Violation)
        if cc['total_cash_breaches'] > 0:
            score += 40
            schemes.append("Zero-Tolerance Cashless Policy Violation (Illicit Cash Handling)")
            anomalies.append(
                f"STRICT POLICY BREACH: Recorded {cc['total_cash_breaches']} transaction(s) using physical CASH "
                f"(Total: ₦{cc['total_cash_amount']:,.2f}) on a 100% cashless platform. Off-the-books funds risk."
            )
            financial_exposure += Decimal(str(cc['total_cash_amount']))

            for s in cc['cash_sales_list']:
                evidence.append({
                    'category': 'Cashless Policy Violation',
                    'detail': f"POS Sale {s['tx_number']} settled with CASH: ₦{s['amount']:,.2f}",
                    'date': s['date'],
                    'notes': f"Customer: {s['guest']}. Cash acceptance is strictly prohibited by hotel policy."
                })

        # B. Check-in Access Code Generated on Unpaid / Pending Bookings
        if cc['unpaid_checkins_count'] > 0:
            score += 35
            schemes.append("Unverified Check-in / Payment Gateway Bypass")
            anomalies.append(
                f"Issued electronic door access codes to {cc['unpaid_checkins_count']} checked-in guest(s) "
                f"with Korapay payment pending or unconfirmed (₦{cc['unpaid_checkins_amount']:,.2f} uncollected)."
            )
            financial_exposure += Decimal(str(cc['unpaid_checkins_amount']))

            for b in cc['suspicious_bookings']:
                if b['status'] == 'checked_in' and b['payment_status'] != 'paid':
                    evidence.append({
                        'category': 'Gateway Bypass Check-in',
                        'detail': f"Booking {b['reference']} (Room {b['room']}): Door key issued with payment {b['payment_status']}",
                        'date': b['date'],
                        'notes': f"Guest: {b['guest']}. Uncollected balance: ₦{b['total'] - b['paid']:,.2f}."
                    })

        # C. Post-Checkin Booking Cancellation (Payment Pocketing / Ledger Wipe)
        if cc['cancelled_after_checkin_count'] > 0:
            score += 45
            schemes.append("Post-Check-in Booking Cancellation (Ledger Wipe)")
            anomalies.append(
                f"{cc['cancelled_after_checkin_count']} booking(s) cancelled AFTER door check-in access code was already generated. "
                f"Total lost revenue exposure: ₦{cc['cancelled_after_checkin_amount']:,.2f}."
            )
            financial_exposure += Decimal(str(cc['cancelled_after_checkin_amount']))

        # D. Ghost Room Charges at POS (Charging Vacant Rooms)
        if cc['ghost_room_charges_count'] > 0:
            score += 40
            schemes.append("Ghost Room Billing (Unoccupied Folio Manipulation)")
            anomalies.append(
                f"Charged {cc['ghost_room_charges_count']} POS / Bar transaction(s) to vacant or unassigned rooms "
                f"(Total: ₦{cc['ghost_room_charges_amount']:,.2f}). Used to conceal missing inventory."
            )
            financial_exposure += Decimal(str(cc['ghost_room_charges_amount']))

            for charge in cc['ghost_room_charges']:
                evidence.append({
                    'category': 'Ghost Room Charge',
                    'detail': f"POS Sale {charge['tx_number']} billed to Room {charge['room']}: ₦{charge['amount']:,.2f}",
                    'date': charge['date'],
                    'notes': charge['reason']
                })

        # =============================================================
        # 3. INVENTORY SHRINKAGE & PHANTOM WASTAGE (NON-CASH THEFT)
        # =============================================================
        if role in ['BAR_STAFF', 'MANAGER']:
            # In a cashless bar, staff steals by writing off drinks as broken/spillage
            if inv['total_shrinkage_value'] > 40000:
                score += 35
                schemes.append("Phantom Liquor Wastage / Stock Write-off Arbitrage")
                anomalies.append(
                    f"Excessive inventory shrinkage logged: ₦{inv['total_shrinkage_value']:,.2f} across "
                    f"{inv['wastage_units'] + inv['neg_adj_units']} units. Wastage-to-sales ratio: {int(inv['wastage_to_sales_ratio']*100)}%."
                )
                financial_exposure += Decimal(str(inv['total_shrinkage_value']))

                for item in inv['suspicious_items']:
                    evidence.append({
                        'category': 'Stock Anomaly',
                        'detail': f"{item['type']}: {item['product']} (Qty: {item['quantity']}) - ₦{item['cost']:,.2f}",
                        'date': item['date'],
                        'notes': item['notes']
                    })
            elif inv['total_shrinkage_value'] > 15000:
                score += 15
                anomalies.append(f"Recorded stock write-offs of ₦{inv['total_shrinkage_value']:,.2f}.")

            # Excessive manual discount overrides
            if inv['discount_count'] >= 3 and inv['total_discount'] > 10000:
                score += 20
                schemes.append("Excessive Pre-Settlement POS Discounting")
                anomalies.append(
                    f"Applied ₦{inv['total_discount']:,.2f} in manual discounts across {inv['discount_count']} transactions."
                )
                financial_exposure += Decimal(str(inv['total_discount']))

            # Off-hours sales activity
            if inv['after_hours_sales'] >= 3:
                score += 15
                anomalies.append(
                    f"{inv['after_hours_sales']} POS orders processed during closed hours (11:00 PM – 05:00 AM)."
                )

        # =============================================================
        # 4. PROCUREMENT & EXPENSES (MANAGEMENT)
        # =============================================================
        if role in ['MANAGER', 'ADMIN']:
            if proc['cash_expense_amount'] > 0:
                score += 20
                schemes.append("Cashless Procurement Policy Bypass")
                anomalies.append(
                    f"Logged ₦{proc['cash_expense_amount']:,.2f} in physical cash expenditures, bypassing verified corporate accounts."
                )
                financial_exposure += Decimal(str(proc['cash_expense_amount']))

            if proc['unreceipted_count'] >= 2:
                score += 20
                schemes.append("Fictitious / Unreceipted Expense Claims")
                anomalies.append(f"{proc['unreceipted_count']} expense vouchers submitted without valid receipt documentation.")

        # Bound score between 0 and 100
        score = min(100, score)

        if score >= 65:
            risk_level = 'CRITICAL'
            fraud_probability = 'Highly Probable'
        elif score >= 45:
            risk_level = 'HIGH'
            fraud_probability = 'Likely'
        elif score >= 25:
            risk_level = 'MEDIUM'
            fraud_probability = 'Suspicious'
        else:
            risk_level = 'LOW'
            fraud_probability = 'Unlikely'

        return {
            'risk_score': score,
            'risk_level': risk_level,
            'fraud_probability': fraud_probability,
            'suspected_schemes': list(set(schemes)),
            'anomalies': anomalies,
            'evidence': evidence,
            'potential_financial_exposure': float(financial_exposure),
        }


class AIFraudExplainer:
    """
    Forensic AI Intelligence Layer:
    Generates plain-English investigative explanations of how staff members exploit
    zero-trust door access codes, evade the cashless Korapay gateway, charge vacant rooms,
    or write off liquor inventory as fake wastage.
    """

    @classmethod
    def generate_explanation(cls, telemetry, evaluation):
        settings = FraudAISettings.get_settings()
        provider = settings.provider
        api_key = settings.api_key or os.environ.get('GROQ_API_KEY') or os.environ.get('GEMINI_API_KEY') or ''

        # If no external API key, or provider set to hybrid, use built-in forensic intelligence
        if not api_key or provider == 'hybrid':
            return cls._generate_smart_heuristic_narrative(telemetry, evaluation)

        try:
            if provider == 'groq':
                return cls._call_groq(telemetry, evaluation, api_key, settings.model_name)
            elif provider == 'gemini':
                return cls._call_gemini(telemetry, evaluation, api_key)
            elif provider == 'xai':
                return cls._call_xai(telemetry, evaluation, api_key)
            else:
                return cls._call_groq(telemetry, evaluation, api_key, settings.model_name)
        except Exception as e:
            logger.warning(f"External AI Provider call failed: {e}. Falling back to Zero-Trust Forensic Engine.")
            return cls._generate_smart_heuristic_narrative(telemetry, evaluation)

    @classmethod
    def _call_groq(cls, telemetry, evaluation, api_key, model_name):
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        prompt = cls._build_prompt(telemetry, evaluation)
        payload = {
            "model": model_name or "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an Elite Forensic Auditor for a Zero-Trust, 100% Cashless Luxury Hotel. "
                        "The hotel does NOT accept cash payments under any circumstance; all transactions run through Korapay. "
                        "All room access is cryptographically controlled via ephemeral RoomAccessCodes (Check-in, Emergency, Cleaning) "
                        "and logged in SecurityAuditLog. "
                        "Analyze staff telemetry for zero-trust key exploitation (ghost stays), cashless gateway evasion, "
                        "ghost room billing to vacant rooms, and phantom inventory shrinkage. "
                        "Respond ONLY with a valid JSON object matching the requested schema."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']
            data = json.loads(content)
            return cls._format_ai_response(data, telemetry, evaluation)
        else:
            raise Exception(f"Groq API returned HTTP {resp.status_code}: {resp.text}")

    @classmethod
    def _call_gemini(cls, telemetry, evaluation, api_key):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        prompt = cls._build_prompt(telemetry, evaluation) + "\n\nFormat your response as pure JSON."
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            content = resp.json()['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(content)
            return cls._format_ai_response(data, telemetry, evaluation)
        else:
            raise Exception(f"Gemini API returned HTTP {resp.status_code}: {resp.text}")

    @classmethod
    def _call_xai(cls, telemetry, evaluation, api_key):
        url = "https://api.x.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        prompt = cls._build_prompt(telemetry, evaluation)
        payload = {
            "model": "grok-beta",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a Zero-Trust Cashless Hotel Forensic Auditor. Output valid JSON explaining employee fraud mechanisms."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content']
            data = json.loads(content)
            return cls._format_ai_response(data, telemetry, evaluation)
        else:
            raise Exception(f"xAI API returned HTTP {resp.status_code}: {resp.text}")

    @classmethod
    def _build_prompt(cls, telemetry, evaluation):
        return f"""
Analyze this employee telemetry in our Zero-Trust, 100% Cashless Hotel platform:
- Staff: {telemetry['full_name']} (Username: {telemetry['username']}, Role: {telemetry['role']})
- Risk Score: {evaluation['risk_score']}/100 ({evaluation['risk_level']})
- Identified Typologies: {json.dumps(evaluation['suspected_schemes'])}
- Behavioral Anomalies: {json.dumps(evaluation['anomalies'])}
- Audit Trail Evidence: {json.dumps(evaluation['evidence'])}
- Zero-Trust Door Security Telemetry: {json.dumps(telemetry['zero_trust'])}
- Cashless Gateway Telemetry: {json.dumps(telemetry['cashless_compliance'])}
- Inventory Shrinkage Telemetry: {json.dumps(telemetry['inventory_shrinkage'])}

Context:
1. The hotel is 100% CASHLESS. Physical cash is strictly forbidden; all payments must settle through Korapay digital channels.
2. The hotel is ZERO-TRUST. Room doors have no physical keys and require dynamic RoomAccessCodes (CHK, EMG, CLN) tracked in SecurityAuditLog.
3. Common fraud patterns: Emergency key arbitrage (ghost stays), Lingering cleaning locks (day-use rentals), Ghost room charges on vacant rooms, Illicit cash handling, and Phantom liquor wastage write-offs.

Provide a JSON object with:
{{
  "verdict_summary": "1-2 sentence executive verdict for the CEO",
  "how_they_might_be_doing_it": "In-depth breakdown of the exact operational manipulation steps and modus operandi",
  "behavioral_red_flags": ["2-4 observable behavioral or system patterns"],
  "recommended_ceo_actions": ["3-5 concrete, discreet investigative actions the CEO should execute immediately"],
  "financial_impact_assessment": "Monetary risk assessment and ongoing exposure"
}}
"""

    @classmethod
    def _format_ai_response(cls, data, telemetry, evaluation):
        return {
            'verdict_summary': data.get('verdict_summary', ''),
            'how_they_might_be_doing_it': data.get('how_they_might_be_doing_it', ''),
            'behavioral_red_flags': data.get('behavioral_red_flags', []),
            'recommended_ceo_actions': data.get('recommended_ceo_actions', []),
            'financial_impact_assessment': data.get('financial_impact_assessment', ''),
        }

    @classmethod
    def _generate_smart_heuristic_narrative(cls, telemetry, evaluation):
        """Zero-Trust, 100% Cashless Offline Forensic Narrative Generator."""
        role = telemetry['role']
        name = telemetry['full_name']
        score = evaluation['risk_score']
        level = evaluation['risk_level']
        schemes = evaluation['suspected_schemes']
        zt = telemetry['zero_trust']
        cc = telemetry['cashless_compliance']
        inv = telemetry['inventory_shrinkage']

        if score < 25:
            return {
                'verdict_summary': f"{name} displays complete compliance with Zero-Trust access protocols and Cashless payment reconciliation.",
                'how_they_might_be_doing_it': "No anomalous activity detected. All door access codes correlate with verified bookings, zero cash transactions recorded, and inventory movements align with verified digital sales.",
                'behavioral_red_flags': [
                    "Zero-trust door code generation strictly matches confirmed guest check-ins",
                    "100% cashless payment compliance with verified digital settlement"
                ],
                'recommended_ceo_actions': [
                    "Maintain standard automated audit monitoring",
                    "No immediate investigative intervention required"
                ],
                'financial_impact_assessment': "Negligible risk. Verified financial exposure is ₦0.00."
            }

        modus_operandi = []
        red_flags = []
        ceo_actions = []

        # 1. Zero-Trust Emergency Key Exploitation
        if "Zero-Trust Emergency Key Exploitation (Ghost Stays)" in schemes:
            modus_operandi.append(
                f"**Emergency Override Key Exploitation (Ghost Stays):** {name} generated "
                f"{zt['emergency_without_booking']} 1-hour emergency access key(s) with no associated guest booking in the system. "
                f"In a zero-trust cashless hotel, rogue staff members generate emergency override keys during late-night shifts "
                f"(e.g., between 11:00 PM and 5:00 AM) to lodge unregistered walk-in guests. Because the platform does not accept cash, "
                f"the staff member instructs the guest to make a private peer-to-peer bank transfer to the staff's personal bank account (OPay/PalmPay), "
                f"bypassing Korapay completely. The hotel receives ₦0 while room utilities and linens are consumed."
            )
            red_flags.append(f"Emergency override codes generated without a linked booking reference ({zt['emergency_without_booking']} occurrences)")
            red_flags.append("Emergency door unlock events occurring during off-hours (midnight to 5:00 AM)")
            ceo_actions.append("Pull CCTV recordings covering the entrance of the flagged room numbers during the exact emergency code generation timestamps.")
            ceo_actions.append("Reconcile electronic door lock event logs against the front desk booking ledger for unrecorded entries.")

        # 2. Housekeeping Cleaning Key Arbitrage
        if "Housekeeping Cleaning Key Arbitrage (Day-Use Stays)" in schemes:
            modus_operandi.append(
                f"**Housekeeping Cleaning Key Arbitrage (Unofficial Day-Use Rentals):** Telemetry detects "
                f"{zt['lingering_cleaning_count']} room(s) held in active cleaning status for over 3 hours. "
                f"The modus operandi involves requesting a cleaning access code (`CLN-...`), receiving manager approval, "
                f"and deliberately delaying the final 'Room Cleaned & Activated' status change. Staff uses this multi-hour shadow window "
                f"to sell unofficial short-rest or day-use stays to patrons, collecting private off-system transfers while the management "
                f"dashboard displays the room as undergoing routine sanitation."
            )
            red_flags.append("Rooms lingering in 'cleaning' status for extended periods (>3 to 18 hours)")
            red_flags.append("Door unlock activity detected on rooms designated as vacant/cleaning")
            ceo_actions.append("Execute an immediate, unannounced physical walk-through of all rooms currently flagged as 'cleaning'.")
            ceo_actions.append("Enforce a strict 60-minute automated timeout on all approved housekeeping cleaning access keys.")

        # 3. Cashless Policy Violation (Illicit Cash Handling)
        if "Zero-Tolerance Cashless Policy Violation (Illicit Cash Handling)" in schemes:
            modus_operandi.append(
                f"**Zero-Tolerance Cashless Policy Breach:** The platform enforces a strict 100% cashless policy via Korapay. "
                f"However, {name} entered {cc['total_cash_breaches']} transaction(s) classified as 'CASH' totaling ₦{cc['total_cash_amount']:,.2f}. "
                f"In a cashless infrastructure, recording cash is an overt red flag: the staff member either accepted unauthorized physical bank notes "
                f"from a patron or logged fictitious transactions to balance unaccounted operational shortages."
            )
            red_flags.append(f"Direct entry of physical cash settlements (₦{cc['total_cash_amount']:,.2f}) on a strictly cashless system")
            red_flags.append("Disregard for automated Korapay virtual account and card payment protocols")
            ceo_actions.append(f"Demand an immediate reconciliation of the ₦{cc['total_cash_amount']:,.2f} cash claimed to be received.")
            ceo_actions.append("Issue a formal compliance warning reaffirming the zero-cash management directive across all departments.")

        # 4. Ghost Room Charges at POS
        if "Ghost Room Billing (Unoccupied Folio Manipulation)" in schemes:
            modus_operandi.append(
                f"**Ghost Room Charges on Vacant Rooms:** Bar/POS telemetry reveals {cc['ghost_room_charges_count']} transaction(s) "
                f"(₦{cc['ghost_room_charges_amount']:,.2f}) billed as `room_charge` to rooms that were vacant, in cleaning, or unassigned. "
                f"In a cashless bar, staff cannot easily steal money from the till. Instead, staff dispenses drinks to friends or illicit buyers, "
                f"and charges the bill to an unoccupied room folio where no guest is physically present to immediately dispute the charge, "
                f"allowing staff to balance daily inventory balances."
            )
            red_flags.append(f"POS room charges routed to vacant or cleaning room numbers ({cc['ghost_room_charges_count']} charges)")
            red_flags.append("Discrepancy between POS dining guest names and active checked-in room guests")
            ceo_actions.append("Cross-reference all room_charge transactions against active guest check-in folios in the bookings table.")
            ceo_actions.append("Configure POS validation to programmatically reject room charges if room status is not 'occupied'.")

        # 5. Unverified Check-in / Gateway Bypass
        if "Unverified Check-in / Payment Gateway Bypass" in schemes or "Post-Check-in Booking Cancellation (Ledger Wipe)" in schemes:
            modus_operandi.append(
                f"**Check-in Gateway Bypass & Ledger Wiping:** Reception telemetry reveals check-in access codes issued "
                f"to guests whose Korapay payment was unverified or still marked 'pending' (₦{cc['unpaid_checkins_amount']:,.2f} total). "
                f"The receptionist provides physical room access without awaiting automated webhook confirmation from Korapay, "
                f"allowing guests to occupy rooms on uncollateralized balances or off-platform private arrangements."
            )
            red_flags.append("Check-in access codes issued prior to automated payment gateway confirmation")
            red_flags.append("Lingering checked-in folios with uncollected balances")
            ceo_actions.append("Audit all active checked-in bookings against Korapay merchant transaction logs to ensure verified settlement.")
            ceo_actions.append("Enable strict zero-trust door key issuance locks that prevent code generation until Korapay status is 'completed'.")

        # 6. Phantom Inventory Wastage
        if "Phantom Liquor Wastage / Stock Write-off Arbitrage" in schemes:
            modus_operandi.append(
                f"**Phantom Liquor Wastage & Shrinkage Exploitation:** {name} has logged ₦{inv['total_shrinkage_value']:,.2f} "
                f"in inventory write-offs classified as 'broken bottles', 'spillage', or 'wastage' across {inv['wastage_units'] + inv['neg_adj_units']} units. "
                f"Because all bar sales are cashless and routed digitally, bar staff cannot pocket till cash directly. "
                f"Instead, staff pours high-value spirits (e.g. Hennessy, premium whiskey) for patrons who send funds to the staff's private accounts, "
                f"subsequently logging the missing bottles as accidental breakage in the system to explain the missing inventory."
            )
            red_flags.append("High concentration of negative stock adjustments on high-margin alcoholic beverages")
            red_flags.append("Breakage/wastage write-offs occurring without supervisory dual-sign-off")
            ceo_actions.append("Conduct an unannounced physical count of all premium liquor inventory against theoretical stock cards.")
            ceo_actions.append("Review bar prep station CCTV footage during the timestamps of recorded bottle breakages.")

        if not modus_operandi:
            modus_operandi.append(
                f"Subtle behavioral and system anomalies detected with a composite score of {score}/100. "
                f"Telemetry reveals minor deviations from zero-trust access control protocols and cashless settlement standards."
            )

        return {
            'verdict_summary': (
                f"Forensic audit detected {level} risk for {name} ({role}) with a Risk Score of {score}/100. "
                f"Identified {len(schemes)} zero-trust / cashless policy deviation(s) with an estimated exposure of ₦{evaluation['potential_financial_exposure']:,.2f}."
            ),
            'how_they_might_be_doing_it': "\n\n".join(modus_operandi),
            'behavioral_red_flags': red_flags or [
                "Discrepancies in zero-trust access code issuance",
                "Non-compliant payment settlement attempts"
            ],
            'recommended_ceo_actions': ceo_actions or [
                "Review electronic door lock security audit trail for flagged rooms",
                "Reconcile daily transaction folios against Korapay merchant dashboard"
            ],
            'financial_impact_assessment': (
                f"Estimated direct financial exposure is approximately ₦{evaluation['potential_financial_exposure']:,.2f}. "
                f"Continued unmonitored operation under these patterns threatens ongoing loss of hotel revenue and room security integrity."
            )
        }


class FraudDetectionPipeline:
    """
    Orchestrates the entire CEO Fraud Radar audit scan across all operational staff.
    """

    @classmethod
    def run_scan(cls, scanned_by_user, days=30, specific_staff_id=None):
        collector = StaffActivityCollector(days=days)
        staff_qs = collector.get_staff_list()

        if specific_staff_id:
            staff_qs = staff_qs.filter(id=specific_staff_id)

        all_results = []
        flagged_count = 0
        critical_count = 0
        high_risk_count = 0
        medium_risk_count = 0
        low_risk_count = 0
        total_potential_loss = Decimal('0.00')

        settings = FraudAISettings.get_settings()

        for staff_user in staff_qs:
            telemetry = collector.collect_for_staff(staff_user)
            evaluation = ForensicAnomalyDetector.evaluate(telemetry)
            ai_narrative = AIFraudExplainer.generate_explanation(telemetry, evaluation)

            # Check existing CEO audit flag
            flag = FraudAuditFlag.objects.filter(staff=staff_user).first()

            result_card = {
                'staff_id': telemetry['staff_id'],
                'username': telemetry['username'],
                'full_name': telemetry['full_name'],
                'role': telemetry['role'],
                'email': telemetry['email'],
                'risk_score': evaluation['risk_score'],
                'risk_level': evaluation['risk_level'],
                'fraud_probability': evaluation['fraud_probability'],
                'suspected_schemes': evaluation['suspected_schemes'],
                'anomalies': evaluation['anomalies'],
                'evidence': evaluation['evidence'],
                'potential_financial_exposure': evaluation['potential_financial_exposure'],
                'verdict_summary': ai_narrative['verdict_summary'],
                'how_they_might_be_doing_it': ai_narrative['how_they_might_be_doing_it'],
                'behavioral_red_flags': ai_narrative['behavioral_red_flags'],
                'recommended_ceo_actions': ai_narrative['recommended_ceo_actions'],
                'financial_impact_assessment': ai_narrative['financial_impact_assessment'],
                'flag_status': flag.status if flag else None,
                'flag_notes': flag.notes if flag else '',
                'telemetry_summary': {
                    'sales_count': telemetry['inventory_shrinkage']['total_sales_count'],
                    'sales_revenue': telemetry['inventory_shrinkage']['total_sales_revenue'],
                    'cash_breaches_count': telemetry['cashless_compliance']['total_cash_breaches'],
                    'cash_breaches_amount': telemetry['cashless_compliance']['total_cash_amount'],
                    'emergency_codes': telemetry['zero_trust']['emergency_codes_created'],
                    'emergency_without_booking': telemetry['zero_trust']['emergency_without_booking'],
                    'lingering_cleaning_locks': telemetry['zero_trust']['lingering_cleaning_count'],
                    'ghost_room_charges': telemetry['cashless_compliance']['ghost_room_charges_count'],
                    'unpaid_checkins': telemetry['cashless_compliance']['unpaid_checkins_count'],
                    'shrinkage_value': telemetry['inventory_shrinkage']['total_shrinkage_value'],
                }
            }

            all_results.append(result_card)

            # Aggregates
            total_potential_loss += Decimal(str(evaluation['potential_financial_exposure']))
            if evaluation['risk_level'] in ['HIGH', 'CRITICAL']:
                flagged_count += 1
            if evaluation['risk_level'] == 'CRITICAL':
                critical_count += 1
            elif evaluation['risk_level'] == 'HIGH':
                high_risk_count += 1
            elif evaluation['risk_level'] == 'MEDIUM':
                medium_risk_count += 1
            else:
                low_risk_count += 1

        # Sort results: highest risk score first
        all_results.sort(key=lambda x: x['risk_score'], reverse=True)

        summary = (
            f"Zero-Trust & Cashless Forensic Audit completed for {len(all_results)} staff members across the last {days} days. "
            f"Detected {critical_count} Critical, {high_risk_count} High, and {medium_risk_count} Medium risk profile(s). "
            f"Total potential loss exposure: ₦{total_potential_loss:,.2f}."
        )

        report = FraudScanReport.objects.create(
            scanned_by=scanned_by_user,
            timeframe_days=days,
            total_staff_analyzed=len(all_results),
            flagged_staff_count=flagged_count,
            high_risk_count=high_risk_count + critical_count,
            medium_risk_count=medium_risk_count,
            low_risk_count=low_risk_count,
            total_potential_loss=total_potential_loss,
            ai_provider_used=settings.provider,
            executive_summary=summary,
            analysis_results=all_results
        )

        return report
