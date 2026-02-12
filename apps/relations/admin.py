from django.contrib import admin
from .models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily

class FixedRelationAdmin(admin.ModelAdmin):
    """Admin for FixedRelation."""
    list_display = ('relation_code', 'default_english', 'default_tamil', 'category', 'max_instances')
    list_filter = ('category',)
    search_fields = ('relation_code', 'default_english', 'default_tamil')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Relation Information', {
            'fields': ('relation_code', 'default_english', 'default_tamil', 'category')
        }),
        ('Gender Restrictions', {
            'fields': ('from_gender', 'to_gender')
        }),
        ('Constraints', {
            'fields': ('max_instances', 'is_reciprocal_required')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

class RelationLanguageReligionAdmin(admin.ModelAdmin):
    """Admin for RelationLanguageReligion."""
    list_display = ('relation', 'language', 'religion', 'label', 'created_at')
    list_filter = ('language', 'religion')
    search_fields = ('relation__relation_code', 'language', 'religion', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

class RelationCasteAdmin(admin.ModelAdmin):
    """Admin for RelationCaste."""
    list_display = ('relation', 'language', 'religion', 'caste', 'label', 'created_at')
    list_filter = ('language', 'religion', 'caste')
    search_fields = ('relation__relation_code', 'language', 'religion', 'caste', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

class RelationFamilyAdmin(admin.ModelAdmin):
    """Admin for RelationFamily."""
    list_display = ('relation', 'family', 'language', 'religion', 'caste', 'label', 'created_at')
    list_filter = ('family', 'language', 'religion', 'caste')
    search_fields = ('relation__relation_code', 'family', 'language', 'religion', 'caste', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

admin.site.register(FixedRelation, FixedRelationAdmin)
admin.site.register(RelationLanguageReligion, RelationLanguageReligionAdmin)
admin.site.register(RelationCaste, RelationCasteAdmin)
admin.site.register(RelationFamily, RelationFamilyAdmin)