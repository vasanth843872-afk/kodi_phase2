from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.conf import settings
from .models import AdminActivityLog

User = settings.AUTH_USER_MODEL

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    if hasattr(user, 'staff_permissions'):
        AdminActivityLog.objects.create(
            user=user,
            action='login',
            description=f'{user.mobile_number} logged in',
            ip_address=get_client_ip(request)
        )

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user and hasattr(user, 'staff_permissions'):
        AdminActivityLog.objects.create(
            user=user,
            action='logout',
            description=f'{user.mobile_number} logged out',
            ip_address=get_client_ip(request)
        )

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')