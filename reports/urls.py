# backend/reports/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('revenue/', views.revenue_report, name='revenue-report'),
    path('sales-summary/', views.sales_summary, name='sales-summary'),
    path('top-products/', views.top_products, name='top-products'),
    path('menu-performance/', views.menu_performance, name='menu-performance'),
    path('inventory/', views.inventory_report, name='inventory-report'),
    path('staff-performance/', views.staff_performance, name='staff-performance'),
    path('occupancy/', views.occupancy_report, name='occupancy-report'),
    path('dashboard-stats/', views.dashboard_stats, name='dashboard-stats'),
    path('export/<str:report_type>/', views.export_report, name='export-report'),
]