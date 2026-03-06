from django.urls import path
from .views import MobileNumberSearchView, MobileNumberAutocompleteView
from . import views

urlpatterns = [
    path('request-otp/', views.RequestOTPView.as_view(), name='request-otp'),
    path('verify-otp/', views.VerifyOTPView.as_view(), name='verify-otp'),
    path('refresh-token/', views.RefreshTokenView.as_view(), name='refresh-token'),
    path('me/', views.UserDetailView.as_view(), name='user-detail'),
    
    # New auto-login endpoints
    path('auto-login/', views.AutoLoginView.as_view(), name='auto-login'),
    path('check-login-status/', views.CheckLoginStatusView.as_view(), name='check-login-status'),
    path('smart-login/', views.SmartLoginView.as_view(), name='smart-login'),  # Recommended
    
    
    path('api/mobile-search/', views.MobileNumberSearchView.as_view(), name='mobile-search'),
    path('api/mobile-autocomplete/', views.MobileNumberAutocompleteView.as_view(), name='mobile-autocomplete'),
]