from django.contrib import admin
from .models import AdminProfile, StaffPermission, AdminActivityLog

@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('admin_id', 'full_name', 'user', 'email', 'department')
    list_filter = ('department', 'created_at')
    search_fields = ('full_name', 'email', 'user__mobile_number')
    readonly_fields = ('admin_id', 'created_at', 'updated_at')

@admin.register(StaffPermission)
class StaffPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_type', 'is_active', 'created_at')
    list_filter = ('user_type', 'is_active', 'created_at')
    search_fields = ('user__mobile_number',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(AdminActivityLog)
class AdminActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('user__mobile_number', 'description')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
# admin_app/admin.py
from django.contrib import admin
from .models import RelationManagementPermission, RelationAdminActivityLog

@admin.register(RelationManagementPermission)
class RelationManagementPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'can_manage_fixed_relations', 'can_manage_family_overrides')
    list_filter = ('can_manage_fixed_relations', 'can_manage_family_overrides')
    search_fields = ('user__mobile_number', 'user__admin_profile__full_name')

@admin.register(RelationAdminActivityLog)
class RelationAdminActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'relation_code', 'created_at')
    list_filter = ('action', 'affected_level')
    search_fields = ('user__mobile_number', 'relation_code', 'description')
    readonly_fields = ('created_at',)
    
    def has_add_permission(self, request):
        return False  # Logs should only be created by the system