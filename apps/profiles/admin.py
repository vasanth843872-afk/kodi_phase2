from django.contrib import admin
from .models import UserProfile

class UserProfileAdmin(admin.ModelAdmin):
    """Admin for UserProfile."""
    list_display = ('user', 'firstname', 'gender', 'lifestyle', 'familyname8', 'created_at')
    list_filter = ('gender', 'lifestyle', 'familyname8')
    search_fields = ('user__mobile_number', 'firstname', 'secondname', 'thirdname')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('STEP-1: Public Information', {
            'fields': (
                'firstname', 'secondname', 'thirdname',
                'fathername1', 'fathername2',
                'mothername1', 'mothername2',
                'gender', 'preferred_language',
                'lifestyle', 'culture_of_life','image'
            )
        }),
        ('STEP-2: Private Information', {
            'fields': (
                'dateofbirth', 'age', 'native',
                'present_city', 'taluk', 'district',
                'state', 'contact_number', 'nationality'
            ),
            'classes': ('collapse',)
        }),
        ('STEP-3: Family Information', {
            'fields': (
                'cultureoflife',
                'familyname1', 'familyname2', 'familyname3',
                'familyname4', 'familyname5'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

admin.site.register(UserProfile, UserProfileAdmin)