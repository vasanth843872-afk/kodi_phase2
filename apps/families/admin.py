from django.contrib import admin
from .models import Family, FamilyInvitation

class FamilyAdmin(admin.ModelAdmin):
    """Admin for Family model."""
    list_display = ('family_name', 'created_by', 'is_locked', 'created_at', 'members_count')
    list_filter = ('is_locked', 'created_at')
    search_fields = ('family_name', 'created_by__mobile_number')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Family Information', {
            'fields': ('family_name', 'description', 'is_locked')
        }),
        ('Creator', {
            'fields': ('created_by',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def members_count(self, obj):
        return obj.get_members_count()
    members_count.short_description = 'Members'

class FamilyInvitationAdmin(admin.ModelAdmin):
    """Admin for FamilyInvitation model."""
    list_display = ('family', 'inviter', 'invitee_mobile', 'status', 'created_at', 'expires_at')
    list_filter = ('status', 'created_at')
    search_fields = ('family__family_name', 'inviter__mobile_number', 'invitee_mobile')
    readonly_fields = ('created_at', 'updated_at', 'expires_at', 'invitation_token')
    fieldsets = (
        ('Invitation Details', {
            'fields': ('family', 'inviter', 'invitee_mobile', 'invitee_user', 'status')
        }),
        ('Token & Expiry', {
            'fields': ('invitation_token', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

admin.site.register(Family, FamilyAdmin)
admin.site.register(FamilyInvitation, FamilyInvitationAdmin)