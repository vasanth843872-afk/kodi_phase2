from django.contrib import admin
from .models import FixedRelation, RelationLanguageLifestyle, RelationFamilyName1, RelationFamily

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

class RelationLanguageLifestyleAdmin(admin.ModelAdmin):
    """Admin for RelationLanguageLifestyle."""
    list_display = ('relation', 'language', 'lifestyle', 'label', 'created_at')
    list_filter = ('language', 'lifestyle')
    search_fields = ('relation__relation_code', 'language', 'lifestyle', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

class RelationFamilyName1Admin(admin.ModelAdmin):
    """Admin for RelationFamilyName1."""
    list_display = ('relation', 'language', 'lifestyle', 'family_name_1', 'label', 'created_at')
    list_filter = ('language', 'lifestyle', 'family_name_1')
    search_fields = ('relation__relation_code', 'language', 'lifestyle', 'family_name_1', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

class RelationFamilyAdmin(admin.ModelAdmin):
    """Admin for RelationFamily."""
    list_display = ('relation', 'family_name_2', 'language', 'lifestyle', 'family_name_1', 'label', 'created_at')
    list_filter = ('family_name_2', 'language', 'lifestyle', 'family_name_1')
    search_fields = ('relation__relation_code', 'family_name_2', 'language', 'lifestyle', 'family_name_1', 'label')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('relation',)

admin.site.register(FixedRelation, FixedRelationAdmin)
admin.site.register(RelationLanguageLifestyle, RelationLanguageLifestyleAdmin)
admin.site.register(RelationFamilyName1, RelationFamilyName1Admin)
admin.site.register(RelationFamily, RelationFamilyAdmin)