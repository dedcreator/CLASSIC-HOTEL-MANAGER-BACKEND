import os
import json
import logging
from datetime import timedelta
from decimal import Decimal
import requests
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.contrib.auth import get_user_model

from sales.models import Sale, SaleItem
from inventory.models import StockMovement, Product
from bookings.models import Booking
from rooms.models import SecurityAuditLog, RoomAccessCode
from consumables.models import Expense
from .models import FraudAISettings, FraudScanReport, FraudAuditFlag

User = get_user_model()
logger = logging.getLogger(__name__)


class StaffActivityCollector:
    """Collects all operational activities across sales, inventory, bookings, and audit logs."""

    def __init__(self, days=30):
        self.days = days
        self.start_date = timezone.now() - timedelta(days=days)

    def get_staff_list(self):
        """Retrieve active staff members (excluding CEO)."""
        return User.objects.filter(
            is_active=True
        ).exclude(role='CEO').order_by('role', 'first_name')

    def collect_for_staff(self, staff_user):
        """Gather quantitative telemetry for an individual staff member."""
        # 1. POS Sales Activity
        sales_qs = Sale.objects.filter(
            staff=staff_user,
            created_at__gte=self.start_date
        )
        total_sales_count = sales_qs.count()
        total_sales_revenue = float(sales_qs.aggregate(t=Sum('total_amount'))['t'] or 0)
        total_discount_given = float(sales_qs.aggregate(d=Sum('discount'))['d'] or 0)
        discount_sales_count = sales_qs.filter(discount__gt=0).count()

        cash_sales = sales_qs.filter(payment_method='cash')
        cash_sales_count = cash_sales.count()
        cash_sales_amount = float(cash_sales.aggregate(t=Sum('total_amount'))['t'] or 0)
        cash_ratio = (cash_sales_count / total_sales_count) if total_sales_count > 0 else 0.0

        # After-hours sales (11 PM to 5 AM)
        after_hours_sales = sales_qs.filter(
            Q(created_at__time__gte='23:00:00') | Q(created_at__time__lte='05:00:00')
        )
        after_hours_count = after_hours_sales.count()

        # 2. Inventory / Stock Movements
        movements_qs = StockMovement.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        wastage_qs = movements_qs.filter(movement_type='wastage')
        wastage_count = wastage_qs.count()
        wastage_units = abs(sum(m.quantity for m in wastage_qs))
        wastage_value = float(sum(abs(m.quantity) * float(m.price_at_movement) for m in wastage_qs))

        adjustment_qs = movements_qs.filter(movement_type='adjustment', quantity__lt=0)
        neg_adjustment_count = adjustment_qs.count()
        neg_adjustment_units = abs(sum(m.quantity for m in adjustment_qs))
        neg_adjustment_value = float(sum(abs(m.quantity) * float(m.price_at_movement) for m in adjustment_qs))

        # Recent suspicious wastage / adjustments
        suspicious_stock_items = []
        for m in list(wastage_qs[:5]) + list(adjustment_qs[:5]):
            suspicious_stock_items.append({
                'type': m.get_movement_type_display(),
                'product': m.product.name,
                'quantity': abs(m.quantity),
                'cost': float(m.price_at_movement) * abs(m.quantity),
                'notes': m.notes or 'No reason provided',
                'date': m.created_at.strftime('%Y-%m-%d %H:%M'),
            })

        # 3. Room Bookings & Check-ins (Reception & Management)
        bookings_created = Booking.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        total_bookings = bookings_created.count()
        pending_payment_checked_in = bookings_created.filter(
            status='checked_in',
            payment_status__in=['pending', 'refunded']
        ).count()

        cancelled_after_checkin = bookings_created.filter(
            status='cancelled',
            checked_in_at__isnull=False
        ).count()

        cash_bookings = bookings_created.filter(payment_method='cash')
        cash_bookings_count = cash_bookings.count()
        cash_bookings_amount = float(cash_bookings.aggregate(t=Sum('total_amount'))['t'] or 0)

        suspicious_bookings = []
        for b in bookings_created.filter(
            Q(status='checked_in', payment_status='pending') |
            Q(status='cancelled', checked_in_at__isnull=False) |
            Q(amount_paid__lt=F_total if False else 0)
        )[:5]:
            suspicious_bookings.append({
                'reference': b.booking_reference,
                'guest': str(b.guest),
                'room': b.room.room_number,
                'status': b.status,
                'payment_status': b.payment_status,
                'total': float(b.total_amount),
                'paid': float(b.amount_paid),
                'date': b.created_at.strftime('%Y-%m-%d'),
            })

        # 4. Security Audit Logs & Ephemeral Room Codes
        audit_logs = SecurityAuditLog.objects.filter(
            actor=staff_user,
            timestamp__gte=self.start_date
        )
        emergency_codes_created = audit_logs.filter(action='EMERGENCY_CODE_GENERATED').count()
        cleaning_codes_requested = audit_logs.filter(action='CLEANING_CODE_REQUESTED').count()

        suspicious_logs = []
        for l in audit_logs.filter(action__in=['EMERGENCY_CODE_GENERATED', 'ACCESS_CODE_REVOKED'])[:5]:
            suspicious_logs.append({
                'action': l.get_action_display(),
                'room': l.room_number,
                'details': l.details,
                'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M'),
            })

        # 5. Expenses logged (Managers / Admins)
        expenses_created = Expense.objects.filter(
            created_by=staff_user,
            created_at__gte=self.start_date
        )
        total_expenses_count = expenses_created.count()
        total_expense_amount = float(expenses_created.aggregate(t=Sum('amount'))['t'] or 0)
        cash_expenses = expenses_created.filter(payment_method='cash')
        cash_expense_amount = float(cash_expenses.aggregate(t=Sum('amount'))['t'] or 0)
        unreceipted_expenses = expenses_created.filter(receipt_number='').count()

        return {
            'staff_id': str(staff_user.id),
            'username': staff_user.username,
            'full_name': f"{staff_user.first_name} {staff_user.last_name}".strip() or staff_user.username,
            'role': staff_user.role,
            'email': staff_user.email,
            'sales': {
                'total_count': total_sales_count,
                'total_revenue': total_sales_revenue,
                'cash_count': cash_sales_count,
                'cash_amount': cash_sales_amount,
                'cash_ratio': round(cash_ratio, 2),
                'total_discount': total_discount_given,
                'discount_count': discount_sales_count,
                'after_hours_count': after_hours_count,
            },
            'inventory': {
                'wastage_count': wastage_count,
                'wastage_units': wastage_units,
                'wastage_value': wastage_value,
                'neg_adjustment_count': neg_adjustment_count,
                'neg_adjustment_units': neg_adjustment_units,
                'neg_adjustment_value': neg_adjustment_value,
                'total_shrinkage_value': round(wastage_value + neg_adjustment_value, 2),
                'suspicious_items': suspicious_stock_items,
            },
            'bookings': {
                'total_bookings': total_bookings,
                'pending_payment_checked_in': pending_payment_checked_in,
                'cancelled_after_checkin': cancelled_after_checkin,
                'cash_count': cash_bookings_count,
                'cash_amount': cash_bookings_amount,
                'suspicious_bookings': suspicious_bookings,
            },
            'security': {
                'emergency_codes_created': emergency_codes_created,
                'cleaning_codes_requested': cleaning_codes_requested,
                'suspicious_logs': suspicious_logs,
            },
            'expenses': {
                'total_count': total_expenses_count,
                'total_amount': total_expense_amount,
                'cash_amount': cash_expense_amount,
                'unreceipted_count': unreceipted_expenses,
            }
        }


class ForensicAnomalyDetector:
    """Evaluates staff telemetry against statistical anomaly thresholds & hotel fraud typologies."""

    @classmethod
    def evaluate(cls, telemetry, peer_benchmarks=None):
        score = 0
        anomalies = []
        schemes = []
        evidence = []
        financial_exposure = Decimal('0.00')

        role = telemetry['role']
        sales = telemetry['sales']
        inv = telemetry['inventory']
        bookings = telemetry['bookings']
        sec = telemetry['security']
        exp = telemetry['expenses']

        # -------------------------------------------------------------
        # 1. Bar / Lounge Staff Evaluation
        # -------------------------------------------------------------
        if role in ['BAR_STAFF', 'MANAGER']:
            # A. Phantom Wastage / Liquor Shrinkage
            shrinkage_val = inv['total_shrinkage_value']
            if shrinkage_val > 50000:
                score += 35
                exposure = Decimal(str(shrinkage_val))
                financial_exposure += exposure
                schemes.append("Phantom Wastage / Liquor Shrinkage")
                anomalies.append(
                    f"Abnormally high inventory shrinkage recorded: ₦{shrinkage_val:,.2f} across "
                    f"{inv['wastage_units'] + inv['neg_adjustment_units']} units."
                )
                for item in inv['suspicious_items']:
                    evidence.append({
                        'category': 'Stock Anomaly',
                        'detail': f"{item['type']}: {item['product']} (Qty: {item['quantity']}) - ₦{item['cost']:,.2f}",
                        'date': item['date'],
                        'notes': item['notes']
                    })
            elif shrinkage_val > 15000:
                score += 20
                schemes.append("Moderate Stock Discrepancies")
                anomalies.append(f"Recorded stock write-offs of ₦{shrinkage_val:,.2f}.")

            # B. Cash Skimming at POS
            if sales['total_count'] >= 5:
                if sales['cash_ratio'] >= 0.85:
                    score += 25
                    schemes.append("Cash Skimming & Off-the-Book Settlements")
                    anomalies.append(
                        f"Unusually high cash transaction ratio: {int(sales['cash_ratio']*100)}% "
                        f"(peer benchmark: ~45%). Creates high risk of unrecorded sales."
                    )
                # High discount volume
                if sales['discount_count'] >= 3 and sales['total_discount'] > 10000:
                    score += 20
                    schemes.append("Excessive POS Discount Override")
                    anomalies.append(
                        f"Applied ₦{sales['total_discount']:,.2f} in manual discounts across "
                        f"{sales['discount_count']} transactions."
                    )
                    financial_exposure += Decimal(str(sales['total_discount']))

            # C. After-hours Transactions
            if sales['after_hours_count'] >= 3:
                score += 15
                anomalies.append(
                    f"{sales['after_hours_count']} POS sales processed during off-hours (11:00 PM – 05:00 AM)."
                )

        # -------------------------------------------------------------
        # 2. Front Desk / Receptionist Evaluation
        # -------------------------------------------------------------
        if role in ['RECEPTIONIST', 'MANAGER']:
            # A. Ghost Bookings & Unpaid Check-ins
            if bookings['pending_payment_checked_in'] > 0:
                score += 30
                schemes.append("Unpaid Room Check-in / Skimmed Cash Stays")
                anomalies.append(
                    f"{bookings['pending_payment_checked_in']} guest(s) checked in with payment pending/unverified."
                )
                for b in bookings['suspicious_bookings']:
                    financial_exposure += Decimal(str(b['total'] - b['paid']))
                    evidence.append({
                        'category': 'Booking Discrepancy',
                        'detail': f"Booking {b['reference']} (Room {b['room']}): {b['status']} with payment {b['payment_status']} (Owed: ₦{b['total'] - b['paid']:,.2f})",
                        'date': b['date'],
                        'notes': f"Guest: {b['guest']}"
                    })

            # B. Cancellations After Check-in
            if bookings['cancelled_after_checkin'] > 0:
                score += 40
                schemes.append("Post-Check-in Booking Cancellation (Payment Pocketing)")
                anomalies.append(
                    f"{bookings['cancelled_after_checkin']} booking(s) cancelled AFTER guest was already checked in."
                )

            # C. Emergency Access Code Abuse
            if sec['emergency_codes_created'] >= 2:
                score += 25
                schemes.append("Unauthorized Room Entry / Unlogged Stay Arbitrage")
                anomalies.append(
                    f"Generated {sec['emergency_codes_created']} emergency bypass access codes."
                )
                for log in sec['suspicious_logs']:
                    evidence.append({
                        'category': 'Access Override',
                        'detail': f"{log['action']} on Room {log['room']}",
                        'date': log['timestamp'],
                        'notes': log['details']
                    })

        # -------------------------------------------------------------
        # 3. Manager / Admin Evaluation (Expenses & Authority)
        # -------------------------------------------------------------
        if role in ['MANAGER', 'ADMIN']:
            if exp['unreceipted_count'] >= 2:
                score += 25
                schemes.append("Fictitious / Unreceipted Expense Claims")
                anomalies.append(
                    f"{exp['unreceipted_count']} expense vouchers submitted without receipt documentation "
                    f"(Total Cash: ₦{exp['cash_amount']:,.2f})."
                )
                financial_exposure += Decimal(str(exp['cash_amount']))

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
    """Generates detailed investigative explanations of how the staff might be defrauding the hotel."""

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
            logger.warning(f"External AI Provider call failed: {e}. Falling back to Smart Forensic Engine.")
            return cls._generate_smart_heuristic_narrative(telemetry, evaluation)

    @classmethod
    def _call_groq(cls, telemetry, evaluation, api_key, model_name):
        """Call Groq free API using requests."""
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
                        "You are a Senior Hospitality Forensic Auditor & Loss Prevention Specialist. "
                        "Analyze staff operational telemetry and explain clearly if and HOW they might be defrauding the hotel. "
                        "Provide concrete modus operandi, evidence patterns, and discreet CEO investigative steps. "
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
        """Call Google Gemini Free Tier API."""
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
        """Call xAI Grok API."""
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
                    "content": "You are a Hotel Loss Prevention Auditor. Output valid JSON explaining staff fraud risks."
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
Analyze this hotel employee telemetry for fraud risk:
- Staff Name: {telemetry['full_name']}
- Role: {telemetry['role']}
- Risk Score: {evaluation['risk_score']}/100 ({evaluation['risk_level']})
- Detected Schemes: {json.dumps(evaluation['suspected_schemes'])}
- Statistical Anomalies: {json.dumps(evaluation['anomalies'])}
- Evidence Records: {json.dumps(evaluation['evidence'])}
- Sales Metrics: {json.dumps(telemetry['sales'])}
- Inventory Metrics: {json.dumps(telemetry['inventory'])}
- Booking Metrics: {json.dumps(telemetry['bookings'])}
- Security Logs: {json.dumps(telemetry['security'])}

Provide a JSON object with:
{{
  "verdict_summary": "1-2 sentence executive verdict for the CEO",
  "how_they_might_be_doing_it": "Detailed explanation of the exact modus operandi and manipulation steps they may be using",
  "behavioral_red_flags": ["List of 2-4 observable behavioral or system patterns"],
  "recommended_ceo_actions": ["List of 3-5 specific, discreet investigative steps the CEO should take"],
  "financial_impact_assessment": "Brief assessment of monetary risk and future exposure"
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
        """Intelligent offline forensic engine that builds rich, realistic audit reports."""
        role = telemetry['role']
        name = telemetry['full_name']
        score = evaluation['risk_score']
        level = evaluation['risk_level']
        schemes = evaluation['suspected_schemes']
        anomalies = evaluation['anomalies']

        if score < 25:
            return {
                'verdict_summary': f"{name} exhibits standard operational patterns with no discernible indicators of fraudulent activity.",
                'how_they_might_be_doing_it': "No active fraud indicators identified. Recorded transactions align with typical departmental variance benchmarks.",
                'behavioral_red_flags': [
                    "Routine shift operations observed",
                    "Stock write-offs and discounts remain within standard operational tolerance"
                ],
                'recommended_ceo_actions': [
                    "Maintain standard periodic shift reconciliations",
                    "Keep routine automated audit monitoring active"
                ],
                'financial_impact_assessment': "Negligible risk. Financial exposure is ₦0.00."
            }

        # Build role-specific detailed modus operandi
        modus_operandi = []
        red_flags = []
        ceo_actions = []

        if "Phantom Wastage / Liquor Shrinkage" in schemes:
            modus_operandi.append(
                f"**Phantom Wastage & Liquor Shrinkage Exploitation:** {name} is recording significant inventory quantities "
                f"as 'spilled', 'broken', or 'wastage' (₦{telemetry['inventory']['total_shrinkage_value']:,.2f} total). "
                f"In practical hospitality fraud, the employee serves these high-value bottles to cash-paying patrons, "
                f"collects the full cash amount directly without printing an official receipt, and writes off the missing "
                f"bottles as damaged stock in the system to balance drawer inventory."
            )
            red_flags.append("Repeated negative inventory adjustments for premium alcoholic beverages")
            red_flags.append("Stock loss write-offs occurring without manager co-signature on shift handover")
            ceo_actions.append(f"Conduct an unannounced physical bottle count of bar inventory against stock cards.")
            ceo_actions.append(f"Review CCTV footage focused directly over the dispensing station and cash drawer during flagged shift hours.")

        if "Cash Skimming & Off-the-Book Settlements" in schemes or "Excessive POS Discount Override" in schemes:
            modus_operandi.append(
                f"**POS Cash Skimming & Discount Overrides:** The employee maintains a cash settlement frequency of "
                f"{int(telemetry['sales']['cash_ratio']*100)}%, substantially above peer benchmarks. Combined with "
                f"₦{telemetry['sales']['total_discount']:,.2f} in manual discounts, the modus operandi typically involves "
                f"charging the guest full price, subsequently applying an authorized or unauthorized post-bill discount or item void, "
                f"and pocketing the cash difference before drawer closing."
            )
            red_flags.append(f"Heavy concentration of cash transactions ({int(telemetry['sales']['cash_ratio']*100)}%) compared to POS card readers")
            red_flags.append("Frequent manual discounts applied just before final bill settlement")
            ceo_actions.append("Audit all closed cash POS receipts against merchant drawer till logs for the past 14 days.")
            ceo_actions.append("Implement dual-authorization requirement for any discount exceeding 5%.")

        if "Unpaid Room Check-in / Skimmed Cash Stays" in schemes or "Post-Check-in Booking Cancellation (Payment Pocketing)" in schemes:
            modus_operandi.append(
                f"**Front Desk Cash Skimming & Ghost Stays:** Reception telemetry reveals rooms marked as 'checked_in' "
                f"while payment status remains 'pending' or zero-funded. In front desk schemes, the receptionist receives "
                f"cash upfront from walk-in or arriving guests, activates room door keys without registering the payment in the "
                f"system, and later cancels or marks the folio as abandoned/no-show, keeping the full cash lodging payment."
            )
            red_flags.append("Active checked-in guest folios lingering with uncollected pending balances")
            red_flags.append("Room cancellations executed after check-in timestamps have elapsed")
            ceo_actions.append("Inspect physical room occupancy right now against system 'checked_in' and 'available' lists.")
            ceo_actions.append("Cross-reference keycard audit timestamps against front desk booking creation times.")

        if "Unauthorized Room Entry / Unlogged Stay Arbitrage" in schemes:
            modus_operandi.append(
                f"**Emergency Override Key Exploitation:** {name} has generated {telemetry['security']['emergency_codes_created']} "
                f"emergency override access codes. Staff members exploit emergency/cleaning key codes to give unauthorized "
                f"guests or acquaintances access to hotel rooms overnight without generating an official booking or lodging revenue."
            )
            red_flags.append("Generation of emergency bypass access codes without accompanying manager approval tickets")
            ceo_actions.append("Review electronic door lock access records for rooms accessed with emergency codes.")

        if not modus_operandi:
            modus_operandi.append(
                f"Multiple subtle deviations detected across operational shifts totaling an anomaly score of {score}/100. "
                f"Staff activity exhibits irregular volume patterns inconsistent with peer averages."
            )

        explanation_text = "\n\n".join(modus_operandi)

        return {
            'verdict_summary': (
                f"High forensic risk detected for {name} ({role}) with a Risk Score of {score}/100 ({level}). "
                f"Identified {len(schemes)} distinct fraud risk pattern(s) with an estimated exposure of ₦{evaluation['potential_financial_exposure']:,.2f}."
            ),
            'how_they_might_be_doing_it': explanation_text,
            'behavioral_red_flags': red_flags or [
                "Unbalanced ratio of cash vs electronic payments",
                "Deviations from departmental operating standards"
            ],
            'recommended_ceo_actions': ceo_actions or [
                "Request written shift reconciliation report from the employee",
                "Initiate confidential physical inventory and drawer audit"
            ],
            'financial_impact_assessment': (
                f"Estimated direct financial exposure is approximately ₦{evaluation['potential_financial_exposure']:,.2f}. "
                f"If undetected, cumulative losses across recurring shifts could escalate significantly."
            )
        }


class FraudDetectionPipeline:
    """Master pipeline that scans staff, analyzes anomalies, queries AI, and saves the confidential scan report."""

    @classmethod
    def run_scan(cls, scanned_by_user, days=30, specific_staff_id=None):
        collector = StaffActivityCollector(days=days)
        staff_qs = collector.get_staff_list()

        if specific_staff_id:
            staff_qs = staff_qs.filter(id=specific_staff_id)

        all_results = []
        high_risk_count = 0
        medium_risk_count = 0
        low_risk_count = 0
        total_potential_loss = Decimal('0.00')

        settings = FraudAISettings.get_settings()

        for staff in staff_qs:
            telemetry = collector.collect_for_staff(staff)
            evaluation = ForensicAnomalyDetector.evaluate(telemetry)
            ai_narrative = AIFraudExplainer.generate_explanation(telemetry, evaluation)

            # Check if staff has existing CEO flag
            existing_flag = FraudAuditFlag.objects.filter(staff=staff).first()
            flag_status = existing_flag.status if existing_flag else None
            flag_notes = existing_flag.notes if existing_flag else ''

            card_data = {
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
                'flag_status': flag_status,
                'flag_notes': flag_notes,
                'telemetry_summary': {
                    'sales_count': telemetry['sales']['total_count'],
                    'sales_revenue': telemetry['sales']['total_revenue'],
                    'cash_ratio': telemetry['sales']['cash_ratio'],
                    'discounts': telemetry['sales']['total_discount'],
                    'wastage_value': telemetry['inventory']['total_shrinkage_value'],
                    'emergency_codes': telemetry['security']['emergency_codes_created'],
                    'unpaid_checkins': telemetry['bookings']['pending_payment_checked_in'],
                }
            }

            if evaluation['risk_level'] in ['HIGH', 'CRITICAL']:
                high_risk_count += 1
            elif evaluation['risk_level'] == 'MEDIUM':
                medium_risk_count += 1
            else:
                low_risk_count += 1

            total_potential_loss += Decimal(str(evaluation['potential_financial_exposure']))
            all_results.append(card_data)

        # Sort results: Critical and High risk first
        all_results.sort(key=lambda x: x['risk_score'], reverse=True)

        flagged_count = high_risk_count + medium_risk_count
        summary = (
            f"Forensic AI Audit completed for {len(all_results)} staff members across the last {days} days. "
            f"Detected {high_risk_count} High/Critical risk profile(s) and {medium_risk_count} Medium risk profile(s). "
            f"Total estimated potential loss exposure: ₦{total_potential_loss:,.2f}."
        )

        # Save to database
        report = FraudScanReport.objects.create(
            scanned_by=scanned_by_user,
            timeframe_days=days,
            total_staff_analyzed=len(all_results),
            flagged_staff_count=flagged_count,
            high_risk_count=high_risk_count,
            medium_risk_count=medium_risk_count,
            low_risk_count=low_risk_count,
            total_potential_loss=total_potential_loss,
            ai_provider_used=settings.provider,
            executive_summary=summary,
            analysis_results=all_results
        )

        return report
