from django.contrib import admin
from .models import Person, PersonRelation

class PersonAdmin(admin.ModelAdmin):
    """Admin for Person model."""
    list_display = ('full_name', 'gender', 'family', 'linked_user', 'is_alive', 'is_verified', 'created_at')
    list_filter = ('gender', 'is_alive', 'is_verified', 'family', 'created_at')
    search_fields = ('full_name', 'family__family_name', 'linked_user__mobile_number')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('linked_user', 'family')
    fieldsets = (
        ('Personal Information', {
            'fields': ('full_name', 'gender', 'date_of_birth', 'date_of_death', 'is_alive')
        }),
        ('Family & User', {
            'fields': ('family', 'linked_user', 'is_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related."""
        queryset = super().get_queryset(request)
        return queryset.select_related('linked_user', 'family')

class PersonRelationAdmin(admin.ModelAdmin):
    """Admin for PersonRelation model."""
    list_display = ('id', 'from_person', 'to_person', 'relation', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'relation', 'created_at')
    search_fields = (
        'from_person__full_name',
        'to_person__full_name',
        'created_by__mobile_number',
        'relation__relation_code'
    )
    readonly_fields = ('created_at', 'updated_at', 'resolved_at')
    raw_id_fields = ('from_person', 'to_person', 'relation', 'created_by', 'resolved_by')
    fieldsets = (
        ('Relation Information', {
            'fields': ('from_person', 'to_person', 'relation', 'status')
        }),
        ('Conflict Resolution', {
            'fields': ('conflict_reason', 'resolved_by', 'resolved_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def get_queryset(self, request):
        """Optimize query with select_related."""
        queryset = super().get_queryset(request)
        return queryset.select_related(
            'from_person', 'to_person', 'relation', 'created_by', 'resolved_by'
        )
    
    def has_change_permission(self, request, obj=None):
        """Admin cannot modify confirmed genealogy truth."""
        if obj and obj.status == 'confirmed':
            return False
        return super().has_change_permission(request, obj)
    
    def has_delete_permission(self, request, obj=None):
        """Admin cannot delete confirmed genealogy truth."""
        if obj and obj.status == 'confirmed':
            return False
        return super().has_delete_permission(request, obj)

admin.site.register(Person, PersonAdmin)
admin.site.register(PersonRelation, PersonRelationAdmin)

from django.contrib import admin
from django.utils import timezone
from datetime import timedelta
from .models import Invitation, Person, PersonRelation

@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'person_info', 'invited_user_info', 'invited_by_info', 'status', 'created_at', 'expiry_status', 'token_display')
    list_filter = ('status', 'created_at')
    search_fields = ('person__full_name', 'invited_user__username', 'invited_user__email', 'invited_user__mobile_number', 'token')
    readonly_fields = ('created_at', 'token', 'accepted_at')
    list_per_page = 25
    
    fieldsets = (
        ('Invitation Details', {
            'fields': ('person', 'invited_user', 'invited_by', 'token', 'status')
        }),
        ('Dates', {
            'fields': ('created_at', 'accepted_at')
        }),
    )
    
    def person_info(self, obj):
        """Display person information."""
        if obj.person:
            return f"{obj.person.full_name} (ID: {obj.person.id})"
        return "-"
    person_info.short_description = 'Person'
    
    def invited_user_info(self, obj):
        """Display invited user information."""
        if obj.invited_user:
            username = getattr(obj.invited_user, 'username', '')
            email = getattr(obj.invited_user, 'email', '')
            mobile = getattr(obj.invited_user, 'mobile_number', '')
            
            info = []
            if username:
                info.append(f"@{username}")
            if email:
                info.append(email)
            if mobile:
                info.append(mobile)
                
            return ' | '.join(info) if info else str(obj.invited_user)
        return "-"
    invited_user_info.short_description = 'Invited User'
    
    def invited_by_info(self, obj):
        """Display inviter information."""
        if obj.invited_by:
            username = getattr(obj.invited_by, 'username', '')
            email = getattr(obj.invited_by, 'email', '')
            mobile = getattr(obj.invited_by, 'mobile_number', '')
            
            info = []
            if username:
                info.append(f"@{username}")
            if email:
                info.append(email)
            if mobile:
                info.append(mobile)
                
            return ' | '.join(info) if info else str(obj.invited_by)
        return "-"
    invited_by_info.short_description = 'Invited By'
    
    def expiry_status(self, obj):
        """Display expiry status."""
        if hasattr(obj, 'expires_at') and obj.expires_at:
            if timezone.now() > obj.expires_at:
                return '⚠️ EXPIRED'
            return 'Active'
        
        # Calculate expiry based on created_at + 7 days
        if hasattr(obj, 'created_at') and obj.created_at:
            expiry_date = obj.created_at + timedelta(days=7)
            if timezone.now() > expiry_date:
                return '⚠️ EXPIRED (auto)'
            return f"Expires in {(expiry_date - timezone.now()).days} days"
        
        return 'Unknown'
    expiry_status.short_description = 'Expiry'
    
    def token_display(self, obj):
        """Display truncated token."""
        if obj.token and len(obj.token) > 20:
            return f"{obj.token[:20]}..."
        return obj.token
    token_display.short_description = 'Token'
    
    def get_queryset(self, request):
        """Optimize queryset for admin."""
        return super().get_queryset(request).select_related(
            'person', 'invited_user', 'invited_by'
        )