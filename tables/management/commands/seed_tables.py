# backend/tables/management/commands/seed_tables.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tables.models import Table

User = get_user_model()

class Command(BaseCommand):
    help = 'Seed sample tables'

    def handle(self, *args, **options):
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

        tables = [
            {'table_number': '1', 'name': 'Garden Terrace', 'capacity': 4, 'section': 'Outdoor'},
            {'table_number': '2', 'name': 'Window Seat', 'capacity': 2, 'section': 'Indoor'},
            {'table_number': '3', 'name': 'VIP Lounge', 'capacity': 6, 'section': 'Indoor'},
            {'table_number': '4', 'name': 'Romantic Corner', 'capacity': 2, 'section': 'Indoor'},
            {'table_number': '5', 'name': 'Family Table', 'capacity': 6, 'section': 'Indoor'},
            {'table_number': '6', 'name': 'Bar Counter', 'capacity': 4, 'section': 'Bar'},
            {'table_number': '7', 'name': 'Terrace View', 'capacity': 4, 'section': 'Outdoor'},
            {'table_number': '8', 'name': 'Private Room', 'capacity': 8, 'section': 'Indoor'},
            {'table_number': '9', 'name': 'Courtyard', 'capacity': 4, 'section': 'Outdoor'},
            {'table_number': '10', 'name': 'Poolside', 'capacity': 6, 'section': 'Outdoor'},
        ]

        for table_data in tables:
            table, created = Table.objects.get_or_create(
                table_number=table_data['table_number'],
                defaults={
                    'name': table_data['name'],
                    'capacity': table_data['capacity'],
                    'section': table_data['section'],
                    'status': 'available',
                    'is_active': True,
                    'created_by': user,
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Created table {table.table_number}: {table.name}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Tables seeded successfully!'))