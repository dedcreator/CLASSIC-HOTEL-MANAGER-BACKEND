from django.test import TestCase
from django.utils import timezone
from datetime import timedelta, datetime, date
from rest_framework.test import APIClient
from accounts.models import User
from rooms.models import Room, RoomAccessCode, SecurityAuditLog
from bookings.models import Guest, Booking
from bookings.views import issue_checkin_access_code

class ZeroTrustAccessControlTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.ceo = User.objects.create_user(username='ceo', password='password123', role='CEO')
        self.manager = User.objects.create_user(username='manager', password='password123', role='MANAGER')
        self.receptionist = User.objects.create_user(username='receptionist', password='password123', role='RECEPTIONIST')
        self.housekeeper = User.objects.create_user(username='housekeeper', password='password123', role='HOUSEKEEPING')

        # Room
        self.room = Room.objects.create(
            room_number='201',
            room_type='standard',
            base_price=25000,
            status='available',
            capacity=2
        )

        # Guest & Booking
        self.guest = Guest.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            phone='08012345678'
        )

        today = date.today()
        tomorrow = today + timedelta(days=1)
        self.booking = Booking.objects.create(
            guest=self.guest,
            room=self.room,
            check_in=today,
            check_out=tomorrow,
            total_nights=1,
            total_amount=25000,
            status='confirmed'
        )

    def test_checkin_access_code_expires_10_minutes_after_stay(self):
        """Check-in access code must be created and expire 10 mins after check-in/stay period"""
        code = issue_checkin_access_code(self.booking, user=self.receptionist)
        self.assertIsNotNone(code)
        self.assertEqual(code.code_type, 'checkin')
        self.assertEqual(code.status, 'active')
        self.assertTrue(code.code.startswith('CHK-'))

        # Check expiration: 10 minutes after checkout time
        expected_checkout_dt = timezone.make_aware(datetime.combine(self.booking.check_out, datetime.min.time().replace(hour=12)))
        expected_expiry = expected_checkout_dt + timedelta(minutes=10)
        self.assertAlmostEqual(code.valid_until.timestamp(), expected_expiry.timestamp(), delta=5)

        # Check audit log
        audit = SecurityAuditLog.objects.filter(action='CHECKIN_CODE_GENERATED', access_code=code.code).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor_username, 'receptionist')
        self.assertEqual(audit.actor_role, 'RECEPTIONIST')

    def test_manager_and_ceo_emergency_key_creation(self):
        """Manager and CEO can create 1-hour emergency key; other roles are forbidden"""
        # Manager can create
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'Water leakage emergency in bathroom'
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        data = resp.data['access_code']
        self.assertTrue(data['code'].startswith('EMG-'))

        # Validity must be 1 hour
        created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        valid_until = datetime.fromisoformat(data['valid_until'].replace('Z', '+00:00'))
        diff_minutes = (valid_until - created_at).total_seconds() / 60
        self.assertAlmostEqual(diff_minutes, 60, delta=1)

        # Room 2 for CEO
        room2 = Room.objects.create(
            room_number='202',
            room_type='deluxe',
            base_price=30000,
            status='available',
            capacity=2
        )

        # CEO can create for another room
        self.client.force_authenticate(user=self.ceo)
        resp_ceo = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(room2.id),
            'reason': 'CEO security inspection'
        }, format='json')
        self.assertEqual(resp_ceo.status_code, 201)

        # Receptionist or Housekeeping cannot create (Forbidden 403)
        self.client.force_authenticate(user=self.receptionist)
        resp_rec = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'Unauthorized attempt'
        }, format='json')
        self.assertEqual(resp_rec.status_code, 403)

    def test_emergency_key_48_hour_cooldown(self):
        """Emergency override key can only be issued once every 48 hours per room"""
        self.client.force_authenticate(user=self.manager)

        # 1st emergency key succeeds
        resp1 = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'First emergency intervention'
        }, format='json')
        self.assertEqual(resp1.status_code, 201)

        # 2nd emergency key within 48 hours fails with 400 Bad Request
        resp2 = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'Second emergency attempt too soon'
        }, format='json')
        self.assertEqual(resp2.status_code, 400)
        self.assertIn('Emergency key cooldown active', resp2.data['error'])

        # Fast forward time beyond 48 hours
        first_code = RoomAccessCode.objects.get(code=resp1.data['access_code']['code'])
        first_code.created_at = timezone.now() - timedelta(hours=49)
        first_code.save()

        # Now issuing another emergency key succeeds
        resp3 = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'Emergency intervention after 48-hour cooldown passed'
        }, format='json')
        self.assertEqual(resp3.status_code, 201)

    def test_housekeeping_cleaning_key_approval_and_activation(self):
        """Housekeeping requests key -> Manager approves -> Room activated back to available"""
        # Step 1: Housekeeping requests cleaning key
        self.client.force_authenticate(user=self.housekeeper)
        req_resp = self.client.post('/api/rooms/access-codes/request_cleaning/', {
            'room_id': str(self.room.id),
            'notes': 'Daily room clean and sanitize'
        }, format='json')
        self.assertEqual(req_resp.status_code, 201)
        code_data = req_resp.data['access_code']
        code_id = code_data['id']
        self.assertEqual(code_data['status'], 'pending_approval')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'cleaning')

        # Non-manager cannot approve
        resp_unauth = self.client.post(f'/api/rooms/access-codes/{code_id}/approve_cleaning/')
        self.assertEqual(resp_unauth.status_code, 403)

        # Step 2: Manager approves cleaning key
        self.client.force_authenticate(user=self.manager)
        app_resp = self.client.post(f'/api/rooms/access-codes/{code_id}/approve_cleaning/')
        self.assertEqual(app_resp.status_code, 200)
        self.assertEqual(app_resp.data['access_code']['status'], 'active')
        self.assertTrue(app_resp.data['access_code']['code'].startswith('CLN-'))

        # Step 3: Housekeeper completes cleaning and activates room
        self.client.force_authenticate(user=self.housekeeper)
        act_resp = self.client.post(f'/api/rooms/access-codes/{code_id}/activate_room/')
        self.assertEqual(act_resp.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'available')

        # Check key marked used
        key_obj = RoomAccessCode.objects.get(id=code_id)
        self.assertEqual(key_obj.status, 'used')

        # Audit logs verify the whole sequence
        logs = SecurityAuditLog.objects.filter(room=self.room).values_list('action', flat=True)
        self.assertIn('CLEANING_CODE_REQUESTED', logs)
        self.assertIn('CLEANING_CODE_APPROVED', logs)
        self.assertIn('ROOM_CLEANED_ACTIVATED', logs)

    def test_access_code_verification(self):
        """Zero-trust code verification verifies valid codes and rejects expired/revoked"""
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post('/api/rooms/access-codes/create_emergency/', {
            'room_id': str(self.room.id),
            'reason': 'Test verification'
        }, format='json')
        code_str = resp.data['access_code']['code']

        # Verify active code
        ver_resp = self.client.post('/api/rooms/access-codes/verify/', {
            'room_id': str(self.room.id),
            'code': code_str
        }, format='json')
        self.assertEqual(ver_resp.status_code, 200)
        self.assertTrue(ver_resp.data['valid'])

        # Verify invalid code
        bad_resp = self.client.post('/api/rooms/access-codes/verify/', {
            'room_id': str(self.room.id),
            'code': 'FAKE-000000'
        }, format='json')
        self.assertEqual(bad_resp.status_code, 404)
        self.assertFalse(bad_resp.data['valid'])
