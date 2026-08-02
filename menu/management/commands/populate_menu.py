# backend/menu/management/commands/populate_menu.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import random
from datetime import datetime, timedelta
from menu.models import Category, MenuItem, Order, OrderItem
from tables.models import Table

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate the menu with sample data for testing'

    def handle(self, *args, **options):
        self.stdout.write('\n🚀 Starting menu population...')
        
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

        # Create Categories
        self.stdout.write('\n📂 Creating categories...')
        categories = self.create_categories(user)

        # Create Menu Items
        self.stdout.write('\n🍽️ Creating menu items...')
        menu_items = self.create_menu_items(categories, user)

        # Create Tables (make sure we get the list)
        self.stdout.write('\n🪑 Creating tables...')
        tables = self.create_tables(user)

        # Only create orders if we have tables
        if tables:
            self.stdout.write('\n📝 Creating sample orders...')
            self.create_orders(menu_items, tables, user)
        else:
            self.stdout.write('\n⚠️ No tables found. Skipping orders.')

        self.stdout.write(self.style.SUCCESS('\n✅ Menu data populated successfully!\n'))

    def create_categories(self, user):
        categories_data = [
            {'name': 'Starters', 'description': 'Delicious appetizers to begin your meal', 'icon': '🥗', 'sort_order': 1},
            {'name': 'Main Course', 'description': 'Hearty and satisfying main dishes', 'icon': '🥩', 'sort_order': 2},
            {'name': 'Pasta', 'description': 'Authentic Italian pasta dishes', 'icon': '🍝', 'sort_order': 3},
            {'name': 'Burgers', 'description': 'Premium gourmet burgers', 'icon': '🍔', 'sort_order': 4},
            {'name': 'Seafood', 'description': 'Fresh seafood delicacies', 'icon': '🦞', 'sort_order': 5},
            {'name': 'Salads', 'description': 'Fresh and healthy salads', 'icon': '🥬', 'sort_order': 6},
            {'name': 'Desserts', 'description': 'Sweet treats to end your meal', 'icon': '🍰', 'sort_order': 7},
            {'name': 'Beverages', 'description': 'Refreshing drinks and beverages', 'icon': '🥤', 'sort_order': 8},
            {'name': 'Cocktails', 'description': 'Signature craft cocktails', 'icon': '🍸', 'sort_order': 9},
            {'name': 'Specials', 'description': 'Chef\'s special creations', 'icon': '⭐', 'sort_order': 10},
        ]

        categories = []
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={
                    'description': cat_data['description'],
                    'icon': cat_data['icon'],
                    'sort_order': cat_data['sort_order'],
                    'is_active': True,
                    'created_by': user,
                }
            )
            categories.append(category)
            if created:
                self.stdout.write(f'  ✅ Created category: {category.name}')
            else:
                self.stdout.write(f'  • Category already exists: {category.name}')
        
        return categories

    def create_menu_items(self, categories, user):
        cat_map = {c.name: c for c in categories}

        menu_items_data = [
            # Starters
            {
                'name': 'Truffle Mushroom Soup',
                'description': 'Creamy wild mushroom soup with truffle oil and fresh herbs',
                'price': 3200,
                'category': 'Starters',
                'is_vegetarian': True,
                'preparation_time': 10,
                'is_popular': True,
                'icon_name': 'HomeIcon',
            },
            {
                'name': 'Bruschetta Classica',
                'description': 'Toasted sourdough with fresh tomatoes, basil, and garlic',
                'price': 2500,
                'category': 'Starters',
                'is_vegetarian': True,
                'preparation_time': 8,
                'is_new': True,
                'icon_name': 'CubeIcon',
            },
            {
                'name': 'Calamari Fritti',
                'description': 'Lightly fried calamari with lemon and aioli',
                'price': 3800,
                'category': 'Starters',
                'preparation_time': 12,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            # Main Course
            {
                'name': 'Grilled Ribeye Steak',
                'description': 'Prime ribeye with garlic butter, served with truffle fries',
                'price': 7800,
                'category': 'Main Course',
                'preparation_time': 25,
                'is_popular': True,
                'icon_name': 'HomeIcon',
            },
            {
                'name': 'Lamb Chops',
                'description': 'Grilled lamb chops with mint sauce and roasted vegetables',
                'price': 8200,
                'category': 'Main Course',
                'preparation_time': 30,
                'is_new': True,
                'icon_name': 'HomeIcon',
            },
            {
                'name': 'Chicken Supreme',
                'description': 'Grilled chicken breast with mushroom cream sauce',
                'price': 5500,
                'category': 'Main Course',
                'preparation_time': 20,
                'is_popular': True,
                'icon_name': 'HomeIcon',
            },
            # Pasta
            {
                'name': 'Spaghetti Carbonara',
                'description': 'Traditional Roman pasta with guanciale, egg yolk, and pecorino',
                'price': 4200,
                'category': 'Pasta',
                'preparation_time': 18,
                'is_popular': True,
                'icon_name': 'HomeIcon',
            },
            {
                'name': 'Truffle Mushroom Risotto',
                'description': 'Creamy Arborio rice with wild mushrooms and truffle oil',
                'price': 4500,
                'category': 'Pasta',
                'is_vegetarian': True,
                'preparation_time': 22,
                'icon_name': 'HomeIcon',
            },
            {
                'name': 'Seafood Linguine',
                'description': 'Fresh pasta with shrimp, mussels, and calamari in white wine sauce',
                'price': 5800,
                'category': 'Pasta',
                'preparation_time': 20,
                'is_new': True,
                'icon_name': 'BeakerIcon',
            },
            # Burgers
            {
                'name': 'Wagyu Beef Burger',
                'description': 'Premium wagyu patty with truffle mayo, arugula, and brioche bun',
                'price': 6800,
                'category': 'Burgers',
                'preparation_time': 18,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Double Cheese Burger',
                'description': 'Double beef patty with cheddar, lettuce, and secret sauce',
                'price': 4500,
                'category': 'Burgers',
                'preparation_time': 15,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Plant-Based Burger',
                'description': 'Beyond Meat patty with vegan cheese and avocado',
                'price': 5200,
                'category': 'Burgers',
                'is_vegetarian': True,
                'is_vegan': True,
                'preparation_time': 15,
                'is_new': True,
                'icon_name': 'BeakerIcon',
            },
            # Seafood
            {
                'name': 'Lobster Thermidor',
                'description': 'Fresh lobster in creamy cognac sauce, gratinated with cheese',
                'price': 8500,
                'category': 'Seafood',
                'preparation_time': 30,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Grilled Salmon',
                'description': 'Fresh Atlantic salmon with lemon butter sauce and asparagus',
                'price': 6200,
                'category': 'Seafood',
                'preparation_time': 22,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Tiger Prawns',
                'description': 'Jumbo prawns with garlic and herbs, served with rice',
                'price': 6800,
                'category': 'Seafood',
                'preparation_time': 20,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            # Salads
            {
                'name': 'Classic Caesar Salad',
                'description': 'Crisp romaine with parmesan, garlic croutons, and house dressing',
                'price': 3200,
                'category': 'Salads',
                'is_vegetarian': True,
                'preparation_time': 10,
                'is_popular': True,
                'icon_name': 'CubeIcon',
            },
            {
                'name': 'Greek Salad',
                'description': 'Fresh tomatoes, cucumber, feta cheese, olives, and oregano',
                'price': 2800,
                'category': 'Salads',
                'is_vegetarian': True,
                'is_vegan': True,
                'preparation_time': 8,
                'icon_name': 'CubeIcon',
            },
            {
                'name': 'Warm Chicken Salad',
                'description': 'Grilled chicken with mixed greens, avocado, and honey mustard dressing',
                'price': 4200,
                'category': 'Salads',
                'preparation_time': 15,
                'is_new': True,
                'icon_name': 'CubeIcon',
            },
            # Desserts
            {
                'name': 'Tiramisu',
                'description': 'Classic Italian dessert with coffee-soaked ladyfingers and mascarpone',
                'price': 2800,
                'category': 'Desserts',
                'is_vegetarian': True,
                'preparation_time': 10,
                'is_popular': True,
                'icon_name': 'CakeIcon',
            },
            {
                'name': 'Chocolate Fondant',
                'description': 'Warm chocolate cake with melting center, vanilla ice cream',
                'price': 3200,
                'category': 'Desserts',
                'is_vegetarian': True,
                'preparation_time': 15,
                'icon_name': 'CakeIcon',
            },
            {
                'name': 'Crème Brûlée',
                'description': 'Classic vanilla custard with caramelized sugar crust',
                'price': 2800,
                'category': 'Desserts',
                'is_vegetarian': True,
                'is_gluten_free': True,
                'preparation_time': 12,
                'is_new': True,
                'icon_name': 'CakeIcon',
            },
            # Beverages
            {
                'name': 'Fresh Lemonade',
                'description': 'House-made lemonade with fresh mint',
                'price': 1500,
                'category': 'Beverages',
                'is_vegetarian': True,
                'is_vegan': True,
                'is_gluten_free': True,
                'preparation_time': 3,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Iced Coffee',
                'description': 'Cold brew coffee with vanilla syrup and milk',
                'price': 1800,
                'category': 'Beverages',
                'is_vegetarian': True,
                'preparation_time': 3,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Fresh Juice Selection',
                'description': 'Seasonal fresh fruit juices (Orange, Apple, Pineapple)',
                'price': 2000,
                'category': 'Beverages',
                'is_vegetarian': True,
                'is_vegan': True,
                'is_gluten_free': True,
                'preparation_time': 5,
                'icon_name': 'BeakerIcon',
            },
            # Cocktails
            {
                'name': 'Signature Old Fashioned',
                'description': 'Bourbon, bitters, sugar, and orange zest',
                'price': 2500,
                'category': 'Cocktails',
                'is_gluten_free': True,
                'preparation_time': 5,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Classic Margarita',
                'description': 'Tequila, triple sec, fresh lime juice, and salt rim',
                'price': 2200,
                'category': 'Cocktails',
                'is_gluten_free': True,
                'is_vegan': True,
                'preparation_time': 5,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Passion Fruit Martini',
                'description': 'Vodka, passion fruit puree, vanilla syrup, and lime',
                'price': 2800,
                'category': 'Cocktails',
                'preparation_time': 5,
                'is_new': True,
                'icon_name': 'BeakerIcon',
            },
            # Specials
            {
                'name': 'Seafood Platter',
                'description': 'Lobster, prawns, calamari, and oysters with dipping sauces',
                'price': 12000,
                'category': 'Specials',
                'preparation_time': 35,
                'is_popular': True,
                'icon_name': 'BeakerIcon',
            },
            {
                'name': 'Chef\'s Tasting Menu',
                'description': '5-course tasting menu with wine pairing',
                'price': 15000,
                'category': 'Specials',
                'preparation_time': 45,
                'is_new': True,
                'icon_name': 'HomeIcon',
            },
        ]

        menu_items = []
        for item_data in menu_items_data:
            category = cat_map.get(item_data['category'])
            if not category:
                self.stdout.write(f'  ⚠️ Category not found: {item_data["category"]}')
                continue

            item, created = MenuItem.objects.get_or_create(
                name=item_data['name'],
                defaults={
                    'description': item_data['description'],
                    'price': Decimal(str(item_data['price'])),
                    'category': category,
                    'is_vegetarian': item_data.get('is_vegetarian', False),
                    'is_vegan': item_data.get('is_vegan', False),
                    'is_gluten_free': item_data.get('is_gluten_free', False),
                    'preparation_time': item_data.get('preparation_time', 15),
                    'is_available': True,
                    'is_popular': item_data.get('is_popular', False),
                    'is_new': item_data.get('is_new', False),
                    'icon_name': item_data.get('icon_name', 'HomeIcon'),
                    'created_by': user,
                }
            )
            menu_items.append(item)
            if created:
                self.stdout.write(f'  ✅ Created menu item: {item.name}')
            else:
                self.stdout.write(f'  • Menu item already exists: {item.name}')

        return menu_items

    def create_tables(self, user):
        tables_data = [
            {'table_number': '1', 'name': 'Garden Terrace', 'capacity': 4, 'section': 'Outdoor', 'status': 'available'},
            {'table_number': '2', 'name': 'Window Seat', 'capacity': 2, 'section': 'Indoor', 'status': 'available'},
            {'table_number': '3', 'name': 'VIP Lounge', 'capacity': 6, 'section': 'Indoor', 'status': 'available'},
            {'table_number': '4', 'name': 'Romantic Corner', 'capacity': 2, 'section': 'Indoor', 'status': 'available'},
            {'table_number': '5', 'name': 'Family Table', 'capacity': 6, 'section': 'Indoor', 'status': 'available'},
            {'table_number': '6', 'name': 'Bar Counter', 'capacity': 4, 'section': 'Bar', 'status': 'available'},
            {'table_number': '7', 'name': 'Terrace View', 'capacity': 4, 'section': 'Outdoor', 'status': 'available'},
            {'table_number': '8', 'name': 'Private Room', 'capacity': 8, 'section': 'Indoor', 'status': 'available'},
            {'table_number': '9', 'name': 'Courtyard', 'capacity': 4, 'section': 'Outdoor', 'status': 'available'},
            {'table_number': '10', 'name': 'Poolside', 'capacity': 6, 'section': 'Outdoor', 'status': 'available'},
            {'table_number': '11', 'name': 'Sky Lounge', 'capacity': 2, 'section': 'Rooftop', 'status': 'available'},
            {'table_number': '12', 'name': 'Indoor Garden', 'capacity': 4, 'section': 'Indoor', 'status': 'available'},
        ]

        tables = []
        for table_data in tables_data:
            table, created = Table.objects.get_or_create(
                table_number=table_data['table_number'],
                defaults={
                    'name': table_data['name'],
                    'capacity': table_data['capacity'],
                    'section': table_data['section'],
                    'status': table_data['status'],
                    'is_active': True,
                    'created_by': user,
                }
            )
            tables.append(table)
            if created:
                # Generate QR code for new tables
                try:
                    table.generate_qr_code()
                    table.save()
                    self.stdout.write(f'  ✅ Created table: {table.table_number} - {table.name} with QR code')
                except Exception as e:
                    self.stdout.write(f'  ✅ Created table: {table.table_number} - {table.name} (QR generation failed: {e})')
            else:
                self.stdout.write(f'  • Table already exists: {table.table_number} - {table.name}')

        return tables

    def create_orders(self, menu_items, tables, user):
        if not tables:
            self.stdout.write('  ⚠️ No tables available to create orders')
            return

        order_count = 0
        # Create orders for the last 7 days
        for day in range(7, -1, -1):
            date = timezone.now().date() - timedelta(days=day)
            num_orders = random.randint(2, 6)

            for _ in range(num_orders):
                table = random.choice(tables)
                num_items = random.randint(1, 4)
                selected_items = random.sample(menu_items, min(num_items, len(menu_items)))

                subtotal = Decimal('0')
                order_items = []

                for item in selected_items:
                    quantity = random.randint(1, 3)
                    item_subtotal = item.price * quantity
                    subtotal += item_subtotal
                    order_items.append({
                        'menu_item': item,
                        'item_name': item.name,
                        'quantity': quantity,
                        'unit_price': item.price,
                        'subtotal': item_subtotal,
                    })

                tax = subtotal * Decimal('0.075')
                total = subtotal + tax

                # Random status based on age
                if day <= 2:
                    status = random.choice(['pending', 'preparing', 'ready', 'served'])
                elif day <= 5:
                    status = random.choice(['ready', 'served', 'paid'])
                else:
                    status = random.choice(['served', 'paid'])

                # Random payment status
                if status in ['paid', 'served']:
                    payment_status = random.choice(['paid', 'pending'])
                else:
                    payment_status = 'pending'

                # Create order
                order = Order.objects.create(
                    table=table,
                    customer_name=random.choice([
                        'John Smith', 'Jane Doe', 'Michael Brown', 'Sarah Wilson', 
                        'David Lee', 'Maria Garcia', 'Robert Taylor', 'Amanda Johnson',
                        'James Williams', 'Patricia Davis'
                    ]),
                    customer_email=random.choice(['guest@example.com', None]),
                    customer_phone=random.choice(['+2348012345678', '+2348023456789', None]),
                    subtotal=subtotal,
                    tax=tax,
                    total_amount=total,
                    status=status,
                    payment_status=payment_status,
                    payment_method=random.choice(['korapay', 'cash', 'card']) if payment_status == 'paid' else None,
                    placed_at=datetime.combine(date, timezone.now().time()) + timedelta(hours=random.randint(10, 22)),
                    created_by=user,
                )

                # Create order items
                for item_data in order_items:
                    OrderItem.objects.create(
                        order=order,
                        menu_item=item_data['menu_item'],
                        item_name=item_data['item_name'],
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price'],
                        subtotal=item_data['subtotal'],
                    )

                # Update order status timestamps
                if status in ['preparing', 'ready', 'served', 'paid']:
                    if status in ['preparing', 'ready']:
                        order.prepared_at = order.placed_at + timedelta(minutes=random.randint(15, 30))
                    if status in ['served', 'paid']:
                        order.served_at = order.placed_at + timedelta(minutes=random.randint(30, 60))
                    if status == 'paid':
                        order.paid_at = order.placed_at + timedelta(minutes=random.randint(45, 90))
                    order.save()
                    order_count += 1

        self.stdout.write(f'  ✅ Created {order_count} sample orders')