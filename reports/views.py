# backend/reports/views.py
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from sales.models import Sale, SaleItem
from menu.models import Order, OrderItem, Category, MenuItem
from inventory.models import Product, StockMovement
from accounts.models import User
from bookings.models import Booking
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def revenue_report(request):
    """Get revenue data for charts - includes sales, orders, and bookings"""
    period = request.query_params.get('period', 'monthly')
    
    today = timezone.now().date()
    
    if period == 'daily':
        # Last 30 days
        start_date = today - timedelta(days=30)
        
        # Sales revenue
        sales = Sale.objects.filter(
            created_at__date__gte=start_date
        ).values('created_at__date').annotate(
            revenue=Sum('total_amount'),
            count=Count('id')
        ).order_by('created_at__date')
        
        # Order revenue
        orders = Order.objects.filter(
            placed_at__date__gte=start_date,
            payment_status='paid'
        ).values('placed_at__date').annotate(
            revenue=Sum('total_amount'),
            count=Count('id')
        ).order_by('placed_at__date')
        
        # Booking revenue
        bookings = Booking.objects.filter(
            check_in__gte=start_date,
            payment_status='paid'
        ).values('check_in').annotate(
            revenue=Sum('total_amount'),
            count=Count('id')
        ).order_by('check_in')
        
    elif period == 'weekly':
        # Last 12 weeks - using raw SQL for SQLite compatibility
        start_date = today - timedelta(weeks=12)
        
        # Sales weekly
        sales = Sale.objects.raw('''
            SELECT 
                strftime("%%Y-%%W", created_at) as week,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM sales_sale
            WHERE created_at >= %s
            GROUP BY week
            ORDER BY week
        ''', [start_date])
        
        # Orders weekly
        orders = Order.objects.raw('''
            SELECT 
                strftime("%%Y-%%W", placed_at) as week,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM menu_order
            WHERE placed_at >= %s AND payment_status = 'paid'
            GROUP BY week
            ORDER BY week
        ''', [start_date])
        
        # Bookings weekly
        bookings = Booking.objects.raw('''
            SELECT 
                strftime("%%Y-%%W", check_in) as week,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM bookings_booking
            WHERE check_in >= %s AND payment_status = 'paid'
            GROUP BY week
            ORDER BY week
        ''', [start_date])
        
    elif period == 'yearly':
        # Last 5 years - using raw SQL for SQLite compatibility
        start_date = today - timedelta(days=365*5)
        
        sales = Sale.objects.raw('''
            SELECT 
                strftime("%%Y", created_at) as year,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM sales_sale
            WHERE created_at >= %s
            GROUP BY year
            ORDER BY year
        ''', [start_date])
        
        orders = Order.objects.raw('''
            SELECT 
                strftime("%%Y", placed_at) as year,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM menu_order
            WHERE placed_at >= %s AND payment_status = 'paid'
            GROUP BY year
            ORDER BY year
        ''', [start_date])
        
        bookings = Booking.objects.raw('''
            SELECT 
                strftime("%%Y", check_in) as year,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM bookings_booking
            WHERE check_in >= %s AND payment_status = 'paid'
            GROUP BY year
            ORDER BY year
        ''', [start_date])
        
    else:  # monthly
        # Last 12 months - using raw SQL for SQLite compatibility
        start_date = today - timedelta(days=365)
        
        sales = Sale.objects.raw('''
            SELECT 
                strftime("%%Y-%%m", created_at) as month,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM sales_sale
            WHERE created_at >= %s
            GROUP BY month
            ORDER BY month
        ''', [start_date])
        
        orders = Order.objects.raw('''
            SELECT 
                strftime("%%Y-%%m", placed_at) as month,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM menu_order
            WHERE placed_at >= %s AND payment_status = 'paid'
            GROUP BY month
            ORDER BY month
        ''', [start_date])
        
        bookings = Booking.objects.raw('''
            SELECT 
                strftime("%%Y-%%m", check_in) as month,
                SUM(total_amount) as revenue,
                COUNT(id) as count
            FROM bookings_booking
            WHERE check_in >= %s AND payment_status = 'paid'
            GROUP BY month
            ORDER BY month
        ''', [start_date])
    
    # Combine all revenue sources
    result = []
    all_dates = set()
    
    # Collect all date keys
    for item in sales:
        key = getattr(item, 'week', getattr(item, 'month', getattr(item, 'year', None)))
        if key:
            all_dates.add(str(key))
    
    for item in orders:
        key = getattr(item, 'week', getattr(item, 'month', getattr(item, 'year', None)))
        if key:
            all_dates.add(str(key))
    
    for item in bookings:
        key = getattr(item, 'week', getattr(item, 'month', getattr(item, 'year', None)))
        if key:
            all_dates.add(str(key))
    
    # Create combined result
    for date_key in sorted(all_dates):
        sale_revenue = 0
        order_revenue = 0
        booking_revenue = 0
        sale_count = 0
        order_count = 0
        booking_count = 0
        
        # Find matching sales
        for s in sales:
            s_key = str(getattr(s, 'week', getattr(s, 'month', getattr(s, 'year', ''))))
            if s_key == date_key:
                sale_revenue = getattr(s, 'revenue', 0) or 0
                sale_count = getattr(s, 'count', 0) or 0
                break
        
        # Find matching orders
        for o in orders:
            o_key = str(getattr(o, 'week', getattr(o, 'month', getattr(o, 'year', ''))))
            if o_key == date_key:
                order_revenue = getattr(o, 'revenue', 0) or 0
                order_count = getattr(o, 'count', 0) or 0
                break
        
        # Find matching bookings
        for b in bookings:
            b_key = str(getattr(b, 'week', getattr(b, 'month', getattr(b, 'year', ''))))
            if b_key == date_key:
                booking_revenue = getattr(b, 'revenue', 0) or 0
                booking_count = getattr(b, 'count', 0) or 0
                break
        
        total_revenue = sale_revenue + order_revenue + booking_revenue
        
        # Calculate expenses (estimate based on total revenue)
        expenses = float(total_revenue) * 0.6
        profit = float(total_revenue) - expenses
        
        result.append({
            'name': date_key,
            'revenue': float(total_revenue),
            'sale_revenue': float(sale_revenue),
            'order_revenue': float(order_revenue),
            'booking_revenue': float(booking_revenue),
            'expenses': expenses,
            'profit': profit,
            'transactions': sale_count + order_count + booking_count,
            'sale_count': sale_count,
            'order_count': order_count,
            'booking_count': booking_count,
        })
    
    return Response(result)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def top_products(request):
    """Get top selling products from sales and menu orders"""
    try:
        limit = int(request.query_params.get('limit', 10))
    except ValueError:
        limit = 10
    
    period = request.query_params.get('period', 'month')
    
    today = timezone.now().date()
    
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    # Top from POS sales
    pos_top = SaleItem.objects.filter(
        sale__created_at__date__gte=start_date
    ).values('product__name', 'product_id').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('subtotal')
    ).order_by('-total_quantity')[:limit]
    
    # Top from Menu orders
    menu_top = OrderItem.objects.filter(
        order__placed_at__date__gte=start_date,
        order__payment_status='paid'
    ).values('item_name', 'menu_item_id').annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('subtotal')
    ).order_by('-total_quantity')[:limit]
    
    # Combine and sort
    combined = []
    
    # Add POS products
    for item in pos_top:
        combined.append({
            'name': item['product__name'] or 'Unknown Product',
            'quantity': item['total_quantity'] or 0,
            'revenue': float(item['total_revenue'] or 0),
            'source': 'POS',
        })
    
    # Add menu items
    for item in menu_top:
        combined.append({
            'name': item['item_name'] or 'Unknown Item',
            'quantity': item['total_quantity'] or 0,
            'revenue': float(item['total_revenue'] or 0),
            'source': 'Menu',
        })
    
    # Sort by quantity and get top
    combined.sort(key=lambda x: x['quantity'], reverse=True)
    top_by_quantity = combined[:limit]
    
    # Sort by revenue
    combined.sort(key=lambda x: x['revenue'], reverse=True)
    top_by_revenue = combined[:limit]
    
    return Response({
        'by_quantity': top_by_quantity,
        'by_revenue': top_by_revenue,
        'period': period,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sales_summary(request):
    """Get sales summary with menu and booking data"""
    period = request.query_params.get('period', 'today')
    
    today = timezone.now().date()
    
    if period == 'today':
        start_date = today
    elif period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today
    
    # Sales summary
    total_sales = Sale.objects.filter(created_at__date__gte=start_date)
    total_revenue = total_sales.aggregate(total=Sum('total_amount'))['total'] or 0
    total_transactions = total_sales.count()
    
    # Payment methods breakdown
    payment_methods = total_sales.values('payment_method').annotate(
        total=Sum('total_amount'),
        count=Count('id')
    )
    
    # Order summary (from menu)
    total_orders = Order.objects.filter(
        placed_at__date__gte=start_date,
        payment_status='paid'
    )
    order_revenue = total_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    order_count = total_orders.count()
    
    # Order status breakdown
    order_status = Order.objects.filter(
        placed_at__date__gte=start_date
    ).values('status').annotate(
        count=Count('id')
    )
    
    # Booking summary
    total_bookings = Booking.objects.filter(
        check_in__gte=start_date,
        payment_status='paid'
    )
    booking_revenue = total_bookings.aggregate(total=Sum('total_amount'))['total'] or 0
    booking_count = total_bookings.count()
    
    # Booking status breakdown
    booking_status = Booking.objects.filter(
        check_in__gte=start_date
    ).values('status').annotate(
        count=Count('id')
    )
    
    return Response({
        'period': period,
        'start_date': start_date.isoformat(),
        'sales': {
            'total_revenue': float(total_revenue),
            'transactions': total_transactions,
            'payment_methods': [
                {
                    'method': p['payment_method'] or 'unknown',
                    'amount': float(p['total'] or 0),
                    'count': p['count']
                }
                for p in payment_methods
            ],
        },
        'orders': {
            'total_revenue': float(order_revenue),
            'count': order_count,
            'statuses': [
                {
                    'status': o['status'],
                    'count': o['count']
                }
                for o in order_status
            ],
        },
        'bookings': {
            'total_revenue': float(booking_revenue),
            'count': booking_count,
            'statuses': [
                {
                    'status': b['status'],
                    'count': b['count']
                }
                for b in booking_status
            ],
        },
        'total_revenue': float(total_revenue + order_revenue + booking_revenue),
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def menu_performance(request):
    """Get menu performance metrics"""
    period = request.query_params.get('period', 'month')
    
    today = timezone.now().date()
    
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    # Get all menu categories
    categories = Category.objects.filter(is_active=True)
    
    result = []
    for category in categories:
        # Get items in this category
        items = MenuItem.objects.filter(category=category, is_available=True)
        
        # Get orders for items in this category
        order_items = OrderItem.objects.filter(
            menu_item__in=items,
            order__placed_at__date__gte=start_date,
            order__payment_status='paid'
        )
        
        total_quantity = order_items.aggregate(total=Sum('quantity'))['total'] or 0
        total_revenue = order_items.aggregate(total=Sum('subtotal'))['total'] or 0
        order_count = order_items.values('order').distinct().count()
        
        # Calculate average order value
        avg_value = total_revenue / order_count if order_count > 0 else 0
        
        result.append({
            'category_id': str(category.id),
            'category_name': category.name,
            'items_count': items.count(),
            'total_orders': order_count,
            'total_quantity': total_quantity,
            'total_revenue': float(total_revenue),
            'avg_order_value': float(avg_value),
        })
    
    # Sort by revenue
    result.sort(key=lambda x: x['total_revenue'], reverse=True)
    
    return Response(result)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """Get all dashboard statistics in one call"""
    today = timezone.now().date()
    start_date = today - timedelta(days=30)  # Last 30 days
    
    # Sales stats
    sales = Sale.objects.filter(created_at__date__gte=start_date)
    total_sales = sales.aggregate(total=Sum('total_amount'))['total'] or 0
    sales_count = sales.count()
    
    # Today's sales
    today_sales = Sale.objects.filter(created_at__date=today)
    today_revenue = today_sales.aggregate(total=Sum('total_amount'))['total'] or 0
    today_count = today_sales.count()
    
    # Orders stats
    orders = Order.objects.filter(
        placed_at__date__gte=start_date,
        payment_status='paid'
    )
    total_orders_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
    orders_count = orders.count()
    
    pending_orders = Order.objects.filter(status__in=['pending', 'preparing']).count()
    
    # Booking stats
    bookings = Booking.objects.filter(
        check_in__gte=start_date,
        payment_status='paid'
    )
    total_booking_revenue = bookings.aggregate(total=Sum('total_amount'))['total'] or 0
    bookings_count = bookings.count()
    
    active_bookings = Booking.objects.filter(status='checked_in').count()
    
    # Total revenue
    total_revenue = total_sales + total_orders_revenue + total_booking_revenue
    
    return Response({
        'period': 'last_30_days',
        'total_revenue': float(total_revenue),
        'sales': {
            'total': float(total_sales),
            'count': sales_count,
            'today_revenue': float(today_revenue),
            'today_count': today_count,
        },
        'orders': {
            'total_revenue': float(total_orders_revenue),
            'count': orders_count,
            'pending': pending_orders,
        },
        'bookings': {
            'total_revenue': float(total_booking_revenue),
            'count': bookings_count,
            'active': active_bookings,
        },
        'summary': {
            'total_transactions': sales_count + orders_count + bookings_count,
            'average_order_value': float(total_revenue / (sales_count + orders_count + bookings_count)) if (sales_count + orders_count + bookings_count) > 0 else 0,
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_report(request):
    """Get inventory summary"""
    # Total products
    total_products = Product.objects.count()
    
    # Low stock items
    low_stock_items = Product.objects.filter(
        current_stock__lte=F('min_stock_level')
    ).count()
    
    # Out of stock
    out_of_stock = Product.objects.filter(current_stock=0).count()
    
    # Total inventory value
    products = Product.objects.all()
    total_value = sum(p.current_stock * p.default_price for p in products if p.current_stock)
    
    # Stock by category
    categories = Product.objects.values('category').annotate(
        total=Sum('current_stock'),
        value=Sum(F('current_stock') * F('default_price'))
    )
    
    # Recent movements
    recent_movements = StockMovement.objects.select_related('product').order_by('-created_at')[:10]
    
    return Response({
        'summary': {
            'total_products': total_products,
            'low_stock': low_stock_items,
            'out_of_stock': out_of_stock,
            'total_value': float(total_value) if total_value else 0,
        },
        'by_category': [
            {
                'category': item['category'] or 'Uncategorized',
                'stock': item['total'] or 0,
                'value': float(item['value']) if item['value'] else 0
            }
            for item in categories if item['category'] is not None
        ],
        'recent_movements': [
            {
                'id': m.id,
                'product': m.product.name,
                'type': m.movement_type,
                'quantity': m.quantity,
                'date': m.created_at,
            }
            for m in recent_movements
        ]
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def staff_performance(request):
    """Get staff performance metrics"""
    period = request.query_params.get('period', 'month')
    
    today = timezone.now().date()
    
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    # Get all staff
    all_staff = User.objects.filter(
        is_active=True, 
        role__in=['BAR_STAFF', 'RECEPTIONIST', 'MANAGER', 'CEO', 'ADMIN']
    )
    
    result = []
    for staff in all_staff:
        # Get sales for this staff member
        sales = Sale.objects.filter(
            created_by=staff,
            created_at__date__gte=start_date
        )
        
        transactions = sales.count()
        revenue = sales.aggregate(total=Sum('total_amount'))['total'] or 0
        avg_sale = revenue / transactions if transactions > 0 else 0
        
        # Get orders handled by this staff (if they're lounge staff)
        orders = Order.objects.filter(
            created_by=staff,
            placed_at__date__gte=start_date,
            payment_status='paid'
        )
        
        order_count = orders.count()
        order_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0
        
        # Get bookings created by this staff (if they're receptionist)
        bookings = Booking.objects.filter(
            created_by=staff,
            created_at__date__gte=start_date,
            payment_status='paid'
        )
        
        booking_count = bookings.count()
        booking_revenue = bookings.aggregate(total=Sum('total_amount'))['total'] or 0
        
        total_handled = transactions + order_count + booking_count
        total_revenue_handled = revenue + order_revenue + booking_revenue
        
        result.append({
            'id': str(staff.id),
            'name': f"{staff.first_name} {staff.last_name}".strip() or staff.username,
            'role': staff.role,
            'transactions': transactions,
            'orders_handled': order_count,
            'bookings_handled': booking_count,
            'total_handled': total_handled,
            'revenue': float(revenue),
            'order_revenue': float(order_revenue),
            'booking_revenue': float(booking_revenue),
            'total_revenue_handled': float(total_revenue_handled),
            'avg_sale': float(avg_sale),
        })
    
    # Sort by total revenue
    result.sort(key=lambda x: x['total_revenue_handled'], reverse=True)
    
    return Response(result)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def occupancy_report(request):
    """Get room occupancy metrics"""
    period = request.query_params.get('period', 'month')
    
    today = timezone.now().date()
    
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    # Get occupancy data
    bookings = Booking.objects.filter(
        check_in__gte=start_date
    ).values('check_in').annotate(
        occupied=Count('id'),
        revenue=Sum('total_amount')
    ).order_by('check_in')
    
    # Calculate occupancy rate (assuming 24 rooms total)
    total_rooms = 24
    
    result = []
    for booking in bookings:
        occupancy_rate = (booking['occupied'] / total_rooms) * 100 if total_rooms > 0 else 0
        result.append({
            'date': booking['check_in'],
            'occupied': booking['occupied'],
            'occupancy_rate': round(occupancy_rate, 2),
            'revenue': float(booking['revenue']) if booking['revenue'] else 0,
        })
    
    return Response(result)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_report(request, report_type):
    """Export report as PDF or Excel"""
    format = request.query_params.get('format', 'pdf')
    period = request.query_params.get('period', 'month')
    
    # This would generate actual PDF/Excel files
    # For now, return a message
    return Response({
        'message': f'Exporting {report_type} report as {format} for period: {period}',
        'download_url': f'/media/reports/{report_type}_{period}.{format}'
    })