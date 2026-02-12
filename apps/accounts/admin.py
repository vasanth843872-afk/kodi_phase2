from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPLog

class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""
    list_display = ('mobile_number', 'is_mobile_verified', 'is_active', 'created_at')
    list_filter = ('is_mobile_verified', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('mobile_number',)
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('mobile_number', 'password')}),
        ('Verification', {'fields': ('is_mobile_verified', 'otp', 'otp_created_at')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    readonly_fields = ('created_at', 'updated_at')
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile_number', 'password1', 'password2'),
        }),
    )

class OTPLogAdmin(admin.ModelAdmin):
    """Admin for OTP logs."""
    list_display = ('mobile_number', 'otp', 'created_at', 'is_used', 'ip_address')
    list_filter = ('is_used', 'created_at')
    search_fields = ('mobile_number', 'ip_address')
    readonly_fields = ('created_at',)

admin.site.register(User, UserAdmin)
admin.site.register(OTPLog, OTPLogAdmin)