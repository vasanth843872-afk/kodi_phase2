from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'events', views.EventViewSet, basename='event')
router.register(r'event-types', views.EventTypeViewSet, basename='event-type')
router.register(r'visibility-levels', views.VisibilityLevelViewSet, basename='visibility-level')
router.register(r'admin/config', views.EventConfigViewSet, basename='admin-config')

urlpatterns = [
    path('', include(router.urls)),
]