from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.FamilyViewSet, basename='family')
router.register(r'invitations', views.FamilyInvitationViewSet, basename='invitation')

urlpatterns = [
    path('', include(router.urls)),
    path('accept-invitation/', 
         views.FamilyViewSet.as_view({'post': 'accept_invitation'}),
         name='accept-invitation'),
]