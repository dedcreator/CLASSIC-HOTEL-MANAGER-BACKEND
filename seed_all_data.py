import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta, date, datetime
from decimal import Decimal
from accounts.models import User
from rooms.models import Room, RoomAccessCode, SecurityAuditLog, log_security_event
from bookings.models import Guest, Booking
from inventory.models import Product, Batch, StockMovement
from menu.models import Category as MenuCategory, MenuItem, Order, OrderItem
from tables.models import Table
from sales.models import Sale, SaleItem

def run_seed():
    print("🚀 Starting full database population...")

    # 1. Users
    print("\n👤 Creating Staff & Admin Users...")
    users_info = [
        ('admin', 'admin@hotel.com', 'admin123', 'CEO', 'Chukwudi', 'Eze', True, True),
        ('manager', 'manager@hotel.com', 'manager123', 'MANAGER', 'Folake', 'Adeyemi', True, False),
        ('reception', 'reception@hotel.com', 'reception123', 'RECEPTIONIST', 'Amina', 'Bello', False, False),
        ('barstaff', 'bar@hotel.com', 'bar123', 'BAR_STAFF', 'Emeka', 'Okafor', False, False),
        ('housekeeping', 'housekeeping@hotel.com', 'housekeeping123', 'HOUSEKEEPING', 'Blessing', 'Effiong', False, False),
    ]

    for uname, email, pwd, role, fname, lname, is_sup, is_stf in users_info:
        u, created = User.objects.get_or_create(username=uname, defaults={'email': email, 'role': role, 'first_name': fname, 'last_name': lname})
        u.email = email
        u.role = role
        u.first_name = fname
        u.last_name = lname
        u.is_active = True
        u.is_staff = True
        u.is_superuser = is_sup
        u.set_password(pwd)
        u.save()
        print(f"  {'✅ Created' if created else '⚡ Updated'} user: {uname} ({role}) - password: {pwd}")

    admin_user = User.objects.get(username='admin')

    # 2. Rooms
    print("\n🏨 Seeding Rooms...")
    rooms_data = [
        {'room_number': '101', 'room_type': 'standard', 'base_price': 15000, 'capacity': 2, 'name': 'Cozy Standard 101', 'description': 'Queen bed, workspace, smart TV, rainfall shower.', 'size': 30, 'amenities': ['WiFi', 'TV', 'AC', 'Safe'], 'status': 'available', 'rating': 4.8, 'review_count': 32},
        {'room_number': '102', 'room_type': 'standard', 'base_price': 18000, 'capacity': 2, 'name': 'Garden Standard 102', 'description': 'Peaceful garden view, natural sunlight, queen bed.', 'size': 32, 'amenities': ['WiFi', 'TV', 'AC', 'Garden View'], 'status': 'available', 'rating': 4.7, 'review_count': 25},
        {'room_number': '103', 'room_type': 'standard', 'base_price': 20000, 'capacity': 2, 'name': 'Executive Standard 103', 'description': 'Fast fiber WiFi, ergonomic desk, minibar.', 'size': 35, 'amenities': ['WiFi', 'TV', 'AC', 'Minibar'], 'status': 'cleaning', 'rating': 4.9, 'review_count': 40},
        {'room_number': '201', 'room_type': 'deluxe', 'base_price': 25000, 'capacity': 2, 'name': 'Deluxe King 201', 'description': 'Plush king bed, private balcony, luxury bathroom.', 'size': 45, 'amenities': ['WiFi', 'TV', 'AC', 'Balcony', 'Bathtub'], 'status': 'occupied', 'rating': 4.9, 'review_count': 58},
        {'room_number': '202', 'room_type': 'deluxe', 'base_price': 28000, 'capacity': 2, 'name': 'Deluxe Skyline 202', 'description': 'Panoramic views, deep soaking tub, espresso bar.', 'size': 50, 'amenities': ['WiFi', 'TV', 'AC', 'City View', 'Bathtub'], 'status': 'available', 'rating': 4.9, 'review_count': 64},
        {'room_number': '203', 'room_type': 'deluxe', 'base_price': 30000, 'capacity': 2, 'name': 'Grand Deluxe 203', 'description': 'Spacious layout with lounge seating and jacuzzi.', 'size': 55, 'amenities': ['WiFi', 'TV', 'AC', 'Jacuzzi'], 'status': 'available', 'rating': 4.8, 'review_count': 44},
        {'room_number': '301', 'room_type': 'suite', 'base_price': 38000, 'capacity': 4, 'name': 'Executive Suite 301', 'description': 'Separate master bedroom, dining space, luxury marble finish.', 'size': 70, 'amenities': ['WiFi', 'TV', 'AC', 'Living Room', 'Bathtub', 'Minibar'], 'status': 'occupied', 'rating': 5.0, 'review_count': 72},
        {'room_number': '302', 'room_type': 'suite', 'base_price': 42000, 'capacity': 4, 'name': 'Family Ambassador Suite 302', 'description': 'Two bedrooms, kitchenette, spacious living area.', 'size': 85, 'amenities': ['WiFi', 'TV', 'AC', 'Kitchenette', 'Living Room'], 'status': 'available', 'rating': 4.9, 'review_count': 39},
        {'room_number': '401', 'room_type': 'executive', 'base_price': 50000, 'capacity': 2, 'name': 'Presidential Penthouse 401', 'description': 'Private terrace, dedicated butler service, infinity view jacuzzi.', 'size': 110, 'amenities': ['WiFi', 'TV', 'AC', 'Terrace', 'Jacuzzi', 'Butler Service', 'Private Bar'], 'status': 'available', 'rating': 5.0, 'review_count': 88, 'is_featured': True},
        {'room_number': '402', 'room_type': 'executive', 'base_price': 55000, 'capacity': 2, 'name': 'Royal Monarch Suite 402', 'description': 'The crown jewel with private rooftop lounge and heated dip pool.', 'size': 130, 'amenities': ['WiFi', 'TV', 'AC', 'Private Pool', 'Terrace', 'Butler Service'], 'status': 'reserved', 'rating': 5.0, 'review_count': 95, 'is_featured': True},
    ]

    for r_data in rooms_data:
        r, _ = Room.objects.update_or_create(room_number=r_data['room_number'], defaults=r_data)
        print(f"  • Room {r.room_number}: {r.name} (₦{r.base_price:,})")

    # 3. Guests & Bookings
    print("\n📅 Seeding Guests & Bookings...")
    guests_data = [
        {'first_name': 'Adebayo', 'last_name': 'Ogunlesi', 'email': 'adebayo.ogunlesi@example.com', 'phone': '+2348031234567', 'id_number': 'NIN-192837461', 'address': 'Victoria Island, Lagos'},
        {'first_name': 'Chioma', 'last_name': 'Nwosu', 'email': 'chioma.nwosu@example.com', 'phone': '+2348059876543', 'id_number': 'NIN-837461928', 'address': 'Maitama, Abuja'},
        {'first_name': 'Babatunde', 'last_name': 'Fashola', 'email': 'babatunde.f@example.com', 'phone': '+2348023456789', 'id_number': 'NIN-746192837', 'address': 'Ikoyi, Lagos'},
        {'first_name': 'Ngozi', 'last_name': 'Okonjo', 'email': 'ngozi.okonjo@example.com', 'phone': '+2348098765432', 'id_number': 'NIN-619283746', 'address': 'Port Harcourt, Rivers'},
        {'first_name': 'David', 'last_name': 'Adeleke', 'email': 'david.adeleke@example.com', 'phone': '+2348101234567', 'id_number': 'NIN-528374619', 'address': 'Lekki Phase 1, Lagos'},
    ]

    guest_objs = []
    for g_data in guests_data:
        g, _ = Guest.objects.get_or_create(email=g_data['email'], defaults=g_data)
        guest_objs.append(g)

    today = date.today()
    r201 = Room.objects.get(room_number='201')
    r301 = Room.objects.get(room_number='301')
    r401 = Room.objects.get(room_number='401')
    r102 = Room.objects.get(room_number='102')

    bookings_data = [
        {
            'guest': guest_objs[0],
            'room': r201,
            'check_in': today - timedelta(days=1),
            'check_out': today + timedelta(days=2),
            'adults': 2,
            'children': 0,
            'total_nights': 3,
            'total_amount': Decimal('75000.00'),
            'amount_paid': Decimal('75000.00'),
            'status': 'checked_in',
            'payment_status': 'paid',
            'payment_method': 'korapay',
            'special_requests': 'High floor, late checkout requested.',
            'checked_in_at': timezone.now() - timedelta(days=1),
            'created_by': admin_user,
        },
        {
            'guest': guest_objs[1],
            'room': r301,
            'check_in': today,
            'check_out': today + timedelta(days=3),
            'adults': 2,
            'children': 1,
            'total_nights': 3,
            'total_amount': Decimal('114000.00'),
            'amount_paid': Decimal('114000.00'),
            'status': 'checked_in',
            'payment_status': 'paid',
            'payment_method': 'card',
            'special_requests': 'Extra pillows and baby cot.',
            'checked_in_at': timezone.now() - timedelta(hours=3),
            'created_by': admin_user,
        },
        {
            'guest': guest_objs[2],
            'room': r401,
            'check_in': today + timedelta(days=2),
            'check_out': today + timedelta(days=5),
            'adults': 2,
            'children': 0,
            'total_nights': 3,
            'total_amount': Decimal('150000.00'),
            'amount_paid': Decimal('150000.00'),
            'status': 'confirmed',
            'payment_status': 'paid',
            'payment_method': 'korapay',
            'special_requests': 'Airport pickup required.',
            'created_by': admin_user,
        },
        {
            'guest': guest_objs[3],
            'room': r102,
            'check_in': today + timedelta(days=4),
            'check_out': today + timedelta(days=6),
            'adults': 1,
            'children': 0,
            'total_nights': 2,
            'total_amount': Decimal('36000.00'),
            'amount_paid': Decimal('0.00'),
            'status': 'confirmed',
            'payment_status': 'pending',
            'payment_method': 'korapay',
            'special_requests': 'Quiet garden side room.',
            'created_by': admin_user,
        },
    ]

    for b_data in bookings_data:
        b, _ = Booking.objects.get_or_create(
            guest=b_data['guest'],
            room=b_data['room'],
            check_in=b_data['check_in'],
            defaults=b_data
        )
        print(f"  • Booking {b.booking_reference}: {b.guest.get_full_name()} (Room {b.room.room_number} - {b.status})")

    # 3b. Zero-Trust Access Codes & Security Audit Logs
    print("\n🔐 Seeding Zero-Trust Ephemeral Access Codes & Security Audit Logs...")
    reception_user = User.objects.get(username='reception')
    housekeeping_user = User.objects.get(username='housekeeping')

    # Checked-in Guest 1 (Room 201)
    b201 = Booking.objects.filter(room=r201, status='checked_in').first()
    if b201:
        checkout_dt = timezone.make_aware(datetime.combine(b201.check_out, datetime.min.time())) + timedelta(hours=11, minutes=10)
        code_201, _ = RoomAccessCode.objects.get_or_create(
            code='CHK-201-9481',
            defaults={
                'code_type': 'checkin',
                'room': r201,
                'booking': b201,
                'status': 'active',
                'created_by': reception_user,
                'approved_by': reception_user,
                'valid_from': b201.checked_in_at or (timezone.now() - timedelta(days=1)),
                'valid_until': checkout_dt,
                'reason': f"Guest Check-in: {b201.guest.get_full_name()}",
            }
        )
        SecurityAuditLog.objects.get_or_create(
            access_code=code_201.code,
            defaults={
                'actor': reception_user,
                'actor_username': reception_user.username,
                'actor_role': reception_user.role,
                'action': 'CHECKIN_CODE_GENERATED',
                'room': r201,
                'room_number': r201.room_number,
                'booking': b201,
                'booking_reference': b201.booking_reference,
                'details': f"Check-in ephemeral access code issued for Guest {b201.guest.get_full_name()}. Valid until 10 mins post-checkout.",
            }
        )
        print(f"  • Room 201 Active Check-in Key: {code_201.code} (Expires: {code_201.valid_until.strftime('%Y-%m-%d %H:%M')})")

    # Checked-in Guest 2 (Room 301)
    b301 = Booking.objects.filter(room=r301, status='checked_in').first()
    if b301:
        checkout_dt_301 = timezone.make_aware(datetime.combine(b301.check_out, datetime.min.time())) + timedelta(hours=11, minutes=10)
        code_301, _ = RoomAccessCode.objects.get_or_create(
            code='CHK-301-4820',
            defaults={
                'code_type': 'checkin',
                'room': r301,
                'booking': b301,
                'status': 'active',
                'created_by': reception_user,
                'approved_by': reception_user,
                'valid_from': b301.checked_in_at or timezone.now(),
                'valid_until': checkout_dt_301,
                'reason': f"Guest Check-in: {b301.guest.get_full_name()}",
            }
        )
        SecurityAuditLog.objects.get_or_create(
            access_code=code_301.code,
            defaults={
                'actor': reception_user,
                'actor_username': reception_user.username,
                'actor_role': reception_user.role,
                'action': 'CHECKIN_CODE_GENERATED',
                'room': r301,
                'room_number': r301.room_number,
                'booking': b301,
                'booking_reference': b301.booking_reference,
                'details': f"Check-in ephemeral access code issued for Guest {b301.guest.get_full_name()}.",
            }
        )
        print(f"  • Room 301 Active Check-in Key: {code_301.code} (Expires: {code_301.valid_until.strftime('%Y-%m-%d %H:%M')})")

    # Cleaning Key Request for Room 103 (Pending Manager Approval)
    r103 = Room.objects.get(room_number='103')
    code_103, _ = RoomAccessCode.objects.get_or_create(
        code='CLN-103-6204',
        defaults={
            'code_type': 'cleaning',
            'room': r103,
            'status': 'pending_approval',
            'created_by': housekeeping_user,
            'valid_from': timezone.now(),
            'valid_until': timezone.now() + timedelta(hours=3),
            'reason': 'Departure room sanitation and linen change.',
        }
    )
    SecurityAuditLog.objects.get_or_create(
        access_code=code_103.code,
        defaults={
            'actor': housekeeping_user,
            'actor_username': housekeeping_user.username,
            'actor_role': housekeeping_user.role,
            'action': 'CLEANING_CODE_REQUESTED',
            'room': r103,
            'room_number': r103.room_number,
            'details': 'Housekeeping cleaning access key requested by Blessing Effiong. Pending Manager authorization.',
        }
    )
    print(f"  • Room 103 Cleaning Key Request: {code_103.code} (Status: {code_103.status} - Awaiting Manager Approval)")

    # 4. Tables
    print("\n🍽️ Seeding Dining Tables...")
    tables_info = [
        ('1', 'Garden Table 1', 'garden-1', 4, 'Indoor Dining', 'Ground', 'available'),
        ('2', 'Garden Table 2', 'garden-2', 4, 'Indoor Dining', 'Ground', 'available'),
        ('3', 'Window Seat 3', 'window-3', 2, 'Indoor Dining', 'Ground', 'occupied'),
        ('4', 'Family Booth 4', 'family-4', 6, 'Indoor Dining', 'Ground', 'available'),
        ('5', 'Terrace Table 5', 'terrace-5', 4, 'Outdoor Terrace', 'Ground', 'available'),
        ('6', 'Terrace Table 6', 'terrace-6', 4, 'Outdoor Terrace', 'Ground', 'available'),
        ('VIP 1', 'Royal VIP Lounge 1', 'vip-1', 8, 'VIP Lounge', 'First', 'available'),
        ('VIP 2', 'Executive VIP Lounge 2', 'vip-2', 10, 'VIP Lounge', 'First', 'available'),
        ('Bar 1', 'Bar High Counter 1', 'bar-1', 2, 'Bar & Lounge', 'Ground', 'available'),
        ('Bar 2', 'Bar High Counter 2', 'bar-2', 2, 'Bar & Lounge', 'Ground', 'occupied'),
    ]

    table_objs = []
    for num, name, slug, cap, sec, flr, st in tables_info:
        t, _ = Table.objects.update_or_create(
            table_number=num,
            defaults={'name': name, 'slug': slug, 'capacity': cap, 'section': sec, 'floor': flr, 'status': st, 'is_active': True, 'created_by': admin_user}
        )
        table_objs.append(t)
        print(f"  • Table {t.table_number}: {t.name} (slug: {t.slug})")

    # 5. Menu Categories & Items
    print("\n🍲 Seeding Menu Categories & Items...")
    categories_info = [
        ('Starters & Small Chops', '🥟', 1),
        ('Main Dishes & Rice', '🍚', 2),
        ('Traditional Soups & Swallows', '🍲', 3),
        ('Grill, Seafood & BBQ', '🥩', 4),
        ('Drinks, Cocktails & Beverages', '🍹', 5),
        ('Desserts & Treats', '🍰', 6),
    ]

    cat_map = {}
    for cname, icon, sorder in categories_info:
        c, _ = MenuCategory.objects.update_or_create(
            name=cname,
            defaults={'icon': icon, 'sort_order': sorder, 'is_active': True, 'created_by': admin_user}
        )
        cat_map[cname] = c

    menu_items_data = [
        # Starters
        {'name': 'Asun (Spicy Peppered Goat Meat)', 'price': Decimal('4500.00'), 'category': cat_map['Starters & Small Chops'], 'description': 'Tender grilled goat meat tossed in spicy scotch bonnet and habanero relish.', 'prep': 15, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Crispy Peppered Chicken Wings (6 pcs)', 'price': Decimal('4000.00'), 'category': cat_map['Starters & Small Chops'], 'description': 'Deep-fried golden chicken wings glazed with signature spicy pepper sauce.', 'prep': 15, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Spring Rolls & Samosa Platter (8 pcs)', 'price': Decimal('3500.00'), 'category': cat_map['Starters & Small Chops'], 'description': 'Crispy vegetable spring rolls and savory beef samosas with sweet chili dip.', 'prep': 10, 'popular': False, 'new': False, 'veg': False},
        {'name': 'Spicy Catfish Pepper Soup', 'price': Decimal('5500.00'), 'category': cat_map['Starters & Small Chops'], 'description': 'Fresh point-and-kill catfish simmered in aromatic Nigerian herbs and spices.', 'prep': 20, 'popular': True, 'new': True, 'veg': False},

        # Mains
        {'name': 'Chef Special Party Jollof Rice & Grilled Quarter Chicken', 'price': Decimal('5500.00'), 'category': cat_map['Main Dishes & Rice'], 'description': 'Smoky firewood-style Jollof rice served with spiced grilled quarter chicken, plantain, and coleslaw.', 'prep': 15, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Seafood Fried Rice with Jumbo Prawns', 'price': Decimal('7500.00'), 'category': cat_map['Main Dishes & Rice'], 'description': 'Wok-tossed basmati rice with calamari, shrimps, diced sweet peppers, and grilled jumbo prawns.', 'prep': 20, 'popular': True, 'new': True, 'veg': False},
        {'name': 'Village Native Pot Rice with Dry Fish & Prawns', 'price': Decimal('6000.00'), 'category': cat_map['Main Dishes & Rice'], 'description': 'Traditional palm oil infused native rice cooked with smoked fish, crayfish, scent leaves, and kpomo.', 'prep': 20, 'popular': False, 'new': True, 'veg': False},

        # Soups & Swallows
        {'name': 'Egusi Soup with Assorted Meat & Pounded Yam', 'price': Decimal('6500.00'), 'category': cat_map['Traditional Soups & Swallows'], 'description': 'Rich melon seed soup with spinach, beef, tripe (shaki), cow foot, stockfish, and smooth pounded yam.', 'prep': 20, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Afang Soup with Goat Meat & Semo', 'price': Decimal('7000.00'), 'category': cat_map['Traditional Soups & Swallows'], 'description': 'Authentic Akwa Ibom style Afang soup prepared with waterleaf, periwinkles, goat meat, and semovita.', 'prep': 25, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Oha Soup with Fresh Fish & Garri (Eba)', 'price': Decimal('6000.00'), 'category': cat_map['Traditional Soups & Swallows'], 'description': 'Delicate Oha leaves cooked with thick cocoyam base, smoked catfish, dried prawns, and yellow garri.', 'prep': 20, 'popular': False, 'new': False, 'veg': False},

        # Grill & BBQ
        {'name': 'Whole Grilled Catfish with Roasted Plantain (Boli)', 'price': Decimal('12000.00'), 'category': cat_map['Grill, Seafood & BBQ'], 'description': 'Whole oven-charred catfish slathered with rich pepper sauce, served with roasted plantain, chips, and coleslaw.', 'prep': 30, 'popular': True, 'new': False, 'veg': False},
        {'name': 'Prime T-Bone Steak with Loaded Mashed Potatoes', 'price': Decimal('16000.00'), 'category': cat_map['Grill, Seafood & BBQ'], 'description': '350g char-grilled aged beef steak with garlic herb butter, peppercorn sauce, and creamed potatoes.', 'prep': 25, 'popular': True, 'new': True, 'veg': False},
        {'name': 'Grilled Jumbo Tiger Prawns (4 pcs)', 'price': Decimal('14000.00'), 'category': cat_map['Grill, Seafood & BBQ'], 'description': 'Marinated in lemon herb garlic butter and flame grilled to perfection with fries.', 'prep': 20, 'popular': False, 'new': True, 'veg': False},

        # Drinks & Cocktails
        {'name': 'Signature Chapman (500ml)', 'price': Decimal('2500.00'), 'category': cat_map['Drinks, Cocktails & Beverages'], 'description': 'Classic Nigerian mocktail with Angostura bitters, Fanta, Sprite, cucumber, and citrus garnish.', 'prep': 5, 'popular': True, 'new': False, 'veg': True},
        {'name': 'Tropical Pina Colada Cocktail', 'price': Decimal('4500.00'), 'category': cat_map['Drinks, Cocktails & Beverages'], 'description': 'White rum, coconut cream, fresh pineapple juice, blended smooth with crushed ice.', 'prep': 5, 'popular': True, 'new': False, 'veg': True},
        {'name': 'Long Island Iced Tea', 'price': Decimal('5500.00'), 'category': cat_map['Drinks, Cocktails & Beverages'], 'description': 'Vodka, gin, rum, tequila, triple sec, sweet & sour splash, and cola float.', 'prep': 5, 'popular': True, 'new': False, 'veg': True},
        {'name': 'Freshly Squeezed Orange Juice', 'price': Decimal('2000.00'), 'category': cat_map['Drinks, Cocktails & Beverages'], 'description': '100% pure fresh farm orange juice served chilled.', 'prep': 5, 'popular': False, 'new': False, 'veg': True},

        # Desserts
        {'name': 'Warm Molten Chocolate Lava Cake', 'price': Decimal('3500.00'), 'category': cat_map['Desserts & Treats'], 'description': 'Decadent warm chocolate cake with a molten fudge core, served with vanilla bean ice cream.', 'prep': 12, 'popular': True, 'new': False, 'veg': True},
        {'name': 'Belgian Waffles with Strawberry & Ice Cream', 'price': Decimal('3800.00'), 'category': cat_map['Desserts & Treats'], 'description': 'Crisp golden waffles drizzled with maple syrup, whipped cream, and fresh strawberries.', 'prep': 12, 'popular': False, 'new': True, 'veg': True},
    ]

    for item_data in menu_items_data:
        m, _ = MenuItem.objects.update_or_create(
            name=item_data['name'],
            defaults={
                'category': item_data['category'],
                'price': item_data['price'],
                'description': item_data['description'],
                'preparation_time': item_data['prep'],
                'is_popular': item_data['popular'],
                'is_new': item_data['new'],
                'is_vegetarian': item_data['veg'],
                'is_available': True,
                'created_by': admin_user,
            }
        )
        print(f"  • Menu Item: {m.name} (₦{m.price:,})")

    # 6. Inventory Products & Batches
    print("\n📦 Seeding Inventory Products & Stock Batches...")
    inventory_items = [
        # Spirits & Whiskeys
        ('Hennessy VS 70cl', 'spirit', Decimal('45000.00'), 'bottle', 24, 6, Decimal('35000.00'), 'bar', True),
        ('Jameson Irish Whiskey 75cl', 'spirit', Decimal('18500.00'), 'bottle', 36, 10, Decimal('14000.00'), 'both', False),
        ('Johnnie Walker Black Label 75cl', 'spirit', Decimal('22000.00'), 'bottle', 30, 8, Decimal('17000.00'), 'both', True),
        ('Glenfiddich 12 Years 70cl', 'spirit', Decimal('38000.00'), 'bottle', 18, 5, Decimal('30000.00'), 'both', True),
        ('Baileys Irish Cream 75cl', 'spirit', Decimal('14000.00'), 'bottle', 24, 6, Decimal('10500.00'), 'bar', False),
        ('Absolut Vodka 75cl', 'spirit', Decimal('12000.00'), 'bottle', 20, 6, Decimal('9000.00'), 'bar', False),

        # Beers
        ('Heineken Lager 330ml Can', 'beer', Decimal('1200.00'), 'can', 120, 30, Decimal('800.00'), 'both', False),
        ('Budweiser 330ml Can', 'beer', Decimal('1000.00'), 'can', 96, 24, Decimal('650.00'), 'both', False),
        ('Guinness Foreign Extra Stout 330ml', 'beer', Decimal('1300.00'), 'bottle', 72, 20, Decimal('850.00'), 'both', False),
        ('Corona Extra 355ml Bottle', 'beer', Decimal('2000.00'), 'bottle', 48, 12, Decimal('1400.00'), 'both', False),
        ('Desperados Tequila Beer 330ml', 'beer', Decimal('1500.00'), 'bottle', 60, 15, Decimal('1000.00'), 'both', False),

        # Wines & Champagne
        ('Moët & Chandon Imperial Brut 75cl', 'champagne', Decimal('95000.00'), 'bottle', 12, 4, Decimal('75000.00'), 'lounge', True),
        ('Veuve Clicquot Yellow Label 75cl', 'champagne', Decimal('110000.00'), 'bottle', 8, 3, Decimal('88000.00'), 'lounge', True),
        ('Nederburg Cabernet Sauvignon 75cl', 'wine', Decimal('9500.00'), 'bottle', 40, 10, Decimal('6800.00'), 'both', False),
        ('Carlo Rossi Sweet Red 75cl', 'wine', Decimal('7000.00'), 'bottle', 50, 12, Decimal('5000.00'), 'both', False),

        # Soft Drinks & Mixers
        ('Coca Cola 500ml Pet', 'soft_drink', Decimal('500.00'), 'bottle', 200, 40, Decimal('320.00'), 'both', False),
        ('Sprite 500ml Pet', 'soft_drink', Decimal('500.00'), 'bottle', 150, 30, Decimal('320.00'), 'both', False),
        ('Schweppes Tonic Water 330ml', 'soft_drink', Decimal('600.00'), 'can', 100, 25, Decimal('400.00'), 'bar', False),
        ('Red Bull Energy Drink 250ml', 'soft_drink', Decimal('1500.00'), 'can', 80, 20, Decimal('1050.00'), 'both', False),
        ('Eva Bottled Natural Water 75cl', 'soft_drink', Decimal('400.00'), 'bottle', 300, 50, Decimal('220.00'), 'both', False),

        # Kitchen Provisions
        ('Mama Gold Premium Parboiled Rice 50kg', 'food', Decimal('85000.00'), 'unit', 10, 3, Decimal('78000.00'), 'both', False),
        ('Golden Penny Pure Vegetable Oil 25L', 'food', Decimal('65000.00'), 'unit', 8, 2, Decimal('58000.00'), 'both', False),
    ]

    for pname, pcat, pprice, punit, pstock, pmin, pcost, ploc, is_prem in inventory_items:
        prod, _ = Product.objects.update_or_create(
            name=pname,
            defaults={
                'category': pcat,
                'default_price': pprice,
                'unit': punit,
                'total_stock': pstock,
                'min_stock_level': pmin,
                'location': ploc,
                'is_premium': is_prem,
                'is_active': True,
                'created_by': admin_user,
            }
        )

        # Create initial batch if none exists
        if not prod.batches.exists():
            batch = Batch.objects.create(
                product=prod,
                quantity=pstock,
                remaining_quantity=pstock,
                cost_price=pcost,
                selling_price=pprice,
                supplier='Grand Beverage & Provision Distributors Ltd',
                batch_number=f"BAT-{prod.name[:3].upper()}-001",
                received_by=admin_user,
            )
            StockMovement.objects.create(
                product=prod,
                batch=batch,
                quantity=pstock,
                movement_type='restock',
                price_at_movement=pcost,
                notes='Initial opening stock seeding',
                created_by=admin_user,
            )
        print(f"  • Inventory Product: {prod.name} (Stock: {prod.total_stock} {prod.unit}s @ ₦{prod.default_price:,})")

    # 7. Sample Live Orders
    print("\n🛎️ Creating Sample Table Orders...")
    t3 = Table.objects.get(table_number='3')
    jollof = MenuItem.objects.get(name__icontains='Jollof')
    asun = MenuItem.objects.get(name__icontains='Asun')
    chapman = MenuItem.objects.get(name__icontains='Chapman')

    order_items = [
        {'menu_item_id': str(jollof.id), 'item_name': jollof.name, 'quantity': 2, 'unit_price': float(jollof.price), 'subtotal': float(jollof.price * 2)},
        {'menu_item_id': str(asun.id), 'item_name': asun.name, 'quantity': 1, 'unit_price': float(asun.price), 'subtotal': float(asun.price)},
        {'menu_item_id': str(chapman.id), 'item_name': chapman.name, 'quantity': 2, 'unit_price': float(chapman.price), 'subtotal': float(chapman.price * 2)},
    ]
    tot = sum(item['subtotal'] for item in order_items)

    sample_order, _ = Order.objects.get_or_create(
        order_number='ORD-2026-0001',
        defaults={
            'table': t3,
            'customer_name': 'Kolawole Johnson',
            'customer_email': 'kola.johnson@example.com',
            'customer_phone': '+2348033445566',
            'items': order_items,
            'subtotal': Decimal(str(tot)),
            'total_amount': Decimal(str(tot)),
            'status': 'preparing',
            'payment_status': 'paid',
            'payment_method': 'korapay',
            'special_instructions': 'Please make the Asun extra spicy, no ice in one Chapman.',
            'created_by': admin_user,
        }
    )
    print(f"  • Order {sample_order.order_number} for Table {sample_order.table.table_number}: ₦{sample_order.total_amount:,} ({sample_order.status})")

    # 8. POS Sales
    print("\n💳 Seeding POS Sales Transactions...")
    bar_user = User.objects.get(username='barstaff')
    heineken = Product.objects.filter(name__icontains='Heineken').first()
    coke = Product.objects.filter(name__icontains='Coca Cola').first()
    whiskey = Product.objects.filter(name__icontains='Jameson').first()

    if heineken and coke:
        if not Sale.objects.filter(guest_name='Adebayo Ogunlesi').exists():
            sale1 = Sale(
                guest_name='Adebayo Ogunlesi',
                room=r201,
                payment_method='room_charge',
                payment_status='completed',
                notes='Room service drinks charged to room folio.',
                staff=bar_user,
            )
            sale1.save()
            SaleItem.objects.create(sale=sale1, product=heineken, quantity=2, unit_price=heineken.default_price)
            SaleItem.objects.create(sale=sale1, product=coke, quantity=2, unit_price=coke.default_price)
            print(f"  • POS Sale {sale1.transaction_number}: ₦{sale1.total_amount:,} charged to Room 201 ({sale1.payment_method})")

        if not Sale.objects.filter(notes__icontains='Walk-in lounge guest').exists():
            sale2 = Sale(
                guest_name='Walk-in Customer',
                payment_method='card',
                payment_status='completed',
                notes='Walk-in lounge guest cocktail & beverage order.',
                staff=bar_user,
            )
            sale2.save()
            if whiskey:
                SaleItem.objects.create(sale=sale2, product=whiskey, quantity=1, unit_price=whiskey.default_price)
            SaleItem.objects.create(sale=sale2, product=coke, quantity=4, unit_price=coke.default_price)
            print(f"  • POS Sale {sale2.transaction_number}: ₦{sale2.total_amount:,} ({sale2.payment_method})")

    print("\n🎉 ALL SEED DATA POPULATED SUCCESSFULLY!")

if __name__ == '__main__':
    run_seed()
