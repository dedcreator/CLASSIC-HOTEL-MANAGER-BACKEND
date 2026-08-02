from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('', views.TableViewSet, basename='table')

urlpatterns = [
    # Public routes MUST come before the router include,
    # otherwise DefaultRouter's detail route (^(?P<pk>[^/.]+)/$)
    # matches "public" as a pk and routes it into TableViewSet
    # (which requires authentication) instead of your public view.
    path('public/', views.public_table_list, name='public-table-list'),
    path('public/<str:slug>/', views.public_table_detail, name='public-table-detail'),

    path('', include(router.urls)),
]