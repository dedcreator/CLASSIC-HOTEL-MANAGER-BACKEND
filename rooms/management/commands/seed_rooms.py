# backend/rooms/management/commands/seed_rooms.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rooms.models import Room
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Seed rooms with sample data for the hotel website'

    def handle(self, *args, **options):
        self.stdout.write('🏨 Seeding rooms...')

        # Get or create admin user
        user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@hotel.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': 'CEO',
                'is_active': True,
                'is_staff': True,
                'is_superuser': True,
            }
        )

        rooms_data = [
            {
                'room_number': '101',
                'room_type': 'standard',
                'base_price': 15000,
                'capacity': 2,
                'name': 'Cozy Standard Room',
                'description': 'A comfortable standard room with all essential amenities for a relaxing stay. Features a plush queen bed, work desk, and modern bathroom.',
                'size': 30,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Work Desk'],
                'rating': 4.7,
                'review_count': 45,
                'is_featured': False,
                'status': 'available',
            },
            {
                'room_number': '102',
                'room_type': 'standard',
                'base_price': 18000,
                'capacity': 2,
                'name': 'Garden View Standard',
                'description': 'Standard room with beautiful garden views and abundant natural light. Perfect for nature lovers seeking tranquility.',
                'size': 35,
                'amenities': ['WiFi', 'TV', 'AC', 'Garden View', 'Balcony'],
                'rating': 4.8,
                'review_count': 38,
                'is_featured': False,
                'status': 'available',
            },
            {
                'room_number': '103',
                'room_type': 'standard',
                'base_price': 20000,
                'capacity': 2,
                'name': 'City View Standard',
                'description': 'Standard room offering stunning city views. Enjoy the vibrant cityscape from the comfort of your room.',
                'size': 32,
                'amenities': ['WiFi', 'TV', 'AC', 'City View', 'Work Desk'],
                'rating': 4.6,
                'review_count': 29,
                'is_featured': False,
                'status': 'available',
            },
            {
                'room_number': '201',
                'room_type': 'deluxe',
                'base_price': 25000,
                'capacity': 2,
                'name': 'Deluxe King Room',
                'description': 'Spacious deluxe room featuring a luxurious king-size bed, premium amenities, and elegant decor. Perfect for a romantic getaway.',
                'size': 45,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'City View'],
                'rating': 4.9,
                'review_count': 67,
                'is_featured': True,
                'status': 'available',
            },
            {
                'room_number': '202',
                'room_type': 'deluxe',
                'base_price': 28000,
                'capacity': 2,
                'name': 'Deluxe Suite',
                'description': 'Luxurious deluxe suite with a separate living area, premium furnishings, and breathtaking views. Experience the ultimate in comfort.',
                'size': 55,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'City View'],
                'rating': 4.9,
                'review_count': 52,
                'is_featured': True,
                'status': 'available',
            },
            {
                'room_number': '203',
                'room_type': 'deluxe',
                'base_price': 30000,
                'capacity': 2,
                'name': 'Deluxe Executive',
                'description': 'Executive deluxe room with premium amenities and a dedicated workspace. Ideal for business travelers seeking comfort and productivity.',
                'size': 50,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Work Desk', 'City View'],
                'rating': 4.8,
                'review_count': 41,
                'is_featured': False,
                'status': 'reserved',
            },
            {
                'room_number': '301',
                'room_type': 'suite',
                'base_price': 35000,
                'capacity': 4,
                'name': 'Executive Suite',
                'description': 'Elegant suite with separate bedroom and living room, perfect for business travelers and families. Features premium amenities and panoramic views.',
                'size': 65,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'City View', 'Work Desk'],
                'rating': 4.8,
                'review_count': 34,
                'is_featured': True,
                'status': 'available',
            },
            {
                'room_number': '302',
                'room_type': 'suite',
                'base_price': 40000,
                'capacity': 4,
                'name': 'Family Suite',
                'description': 'Spacious suite designed for families with two bedrooms, a shared living area, and a kitchenette. Perfect for creating lasting memories.',
                'size': 75,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'Kitchenette', 'City View'],
                'rating': 4.7,
                'review_count': 28,
                'is_featured': False,
                'status': 'available',
            },
            {
                'room_number': '303',
                'room_type': 'suite',
                'base_price': 45000,
                'capacity': 4,
                'name': 'Penthouse Suite',
                'description': 'Luxurious penthouse suite with panoramic views, private terrace, and premium amenities. The ultimate in luxury and sophistication.',
                'size': 85,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'Terrace', 'City View', 'Private Bar'],
                'rating': 4.9,
                'review_count': 19,
                'is_featured': True,
                'status': 'available',
            },
            {
                'room_number': '401',
                'room_type': 'executive',
                'base_price': 50000,
                'capacity': 2,
                'name': 'Presidential Suite',
                'description': 'The epitome of luxury with panoramic views, private terrace, and butler service. Experience royalty in our most prestigious suite.',
                'size': 100,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'Terrace', 'City View', 'Butler Service', 'Private Dining'],
                'rating': 5.0,
                'review_count': 12,
                'is_featured': True,
                'status': 'available',
            },
            {
                'room_number': '402',
                'room_type': 'executive',
                'base_price': 55000,
                'capacity': 2,
                'name': 'Royal Suite',
                'description': 'Our most exclusive suite with stunning views, private pool, and personalized service. The pinnacle of luxury living.',
                'size': 120,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'Private Pool', 'Terrace', 'City View', 'Butler Service', 'Private Bar'],
                'rating': 5.0,
                'review_count': 8,
                'is_featured': True,
                'status': 'reserved',
            },
            {
                'room_number': '403',
                'room_type': 'executive',
                'base_price': 48000,
                'capacity': 2,
                'name': 'Executive Premier',
                'description': 'Premier executive room with state-of-the-art amenities, panoramic views, and personalized service. Designed for the discerning traveler.',
                'size': 90,
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar', 'Safe', 'Bathtub', 'Living Room', 'City View', 'Work Desk', 'Concierge Service'],
                'rating': 4.9,
                'review_count': 15,
                'is_featured': False,
                'status': 'cleaning',
            },
        ]

        created_count = 0
        updated_count = 0

        for room_data in rooms_data:
            # Check if room exists
            room, created = Room.objects.get_or_create(
                room_number=room_data['room_number'],
                defaults={
                    'room_type': room_data['room_type'],
                    'base_price': room_data['base_price'],
                    'capacity': room_data['capacity'],
                    'name': room_data['name'],
                    'description': room_data['description'],
                    'size': room_data['size'],
                    'amenities': room_data['amenities'],
                    'rating': room_data['rating'],
                    'review_count': room_data['review_count'],
                    'is_featured': room_data['is_featured'],
                    'status': room_data['status'],
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ Created room {room.room_number}: {room.name}'))
            else:
                # Update existing room with new fields
                updated_count += 1
                room.room_type = room_data['room_type']
                room.base_price = room_data['base_price']
                room.capacity = room_data['capacity']
                room.name = room_data['name']
                room.description = room_data['description']
                room.size = room_data['size']
                room.amenities = room_data['amenities']
                room.rating = room_data['rating']
                room.review_count = room_data['review_count']
                room.is_featured = room_data['is_featured']
                room.status = room_data['status']
                room.save()
                self.stdout.write(f'• Updated room {room.room_number}: {room.name}')

        self.stdout.write(self.style.SUCCESS(f'\n✅ Rooms seeded successfully!'))
        self.stdout.write(f'   Created: {created_count} rooms')
        self.stdout.write(f'   Updated: {updated_count} rooms')

        # Show summary of room statuses
        status_counts = {}
        for room in Room.objects.all():
            status_counts[room.status] = status_counts.get(room.status, 0) + 1

        self.stdout.write('\n📊 Room Status Summary:')
        for status, count in status_counts.items():
            self.stdout.write(f'   • {status}: {count} rooms')