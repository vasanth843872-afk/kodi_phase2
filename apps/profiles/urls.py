from django.urls import path
from . import views

urlpatterns = [
    path('me/', views.MyProfileView.as_view(), name='my-profile'),
    path('public/<int:user_id>/', views.PublicProfileView.as_view(), name='public-profile'),
    path('completion-status/', views.ProfileCompletionStatusView.as_view(), name='profile-completion'),
]