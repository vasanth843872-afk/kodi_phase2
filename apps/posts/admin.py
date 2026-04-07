from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    Post, PostVisibilityRule, PostComment, PostLike, 
    PostShare, PostSave, PostReport, PostMedia, PostAudience
)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Admin interface for Post model."""
    
    list_display = [
        'id', 'author_info', 'content_preview', 'visibility',
        'engagement_stats', 'is_active', 'is_reported', 'created_at'
    ]
    list_filter = [
        'visibility', 'is_active', 'is_deleted', 'is_reported',
        'created_at', 'updated_at'
    ]
    search_fields = ['content', 'author__mobile_number']
    readonly_fields = [
        'id', 'likes_count', 'comments_count', 'shares_count',
        'created_at', 'updated_at'
    ]
    raw_id_fields = ['author', 'custom_visibility_rule']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('author', 'content', 'visibility', 'custom_visibility_rule')
        }),
        ('Engagement', {
            'fields': ('likes_count', 'comments_count', 'shares_count'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_deleted', 'is_reported')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['soft_delete_posts', 'restore_posts', 'mark_as_not_reported']
    
    def author_info(self, obj):
        """Display author information with link."""
        if obj.author:
            url = reverse('admin:accounts_user_change', args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', url, obj.author.mobile_number)
        return '-'
    author_info.short_description = 'Author'
    
    def content_preview(self, obj):
        """Display shortened content."""
        if len(obj.content) > 100:
            return obj.content[:100] + '...'
        return obj.content
    content_preview.short_description = 'Content'
    
    def engagement_stats(self, obj):
        """Display engagement statistics."""
        return format_html(
            '❤️ {} 💬 {} 🔄 {}',
            obj.likes_count,
            obj.comments_count,
            obj.shares_count
        )
    engagement_stats.short_description = 'Engagement'
    
    def soft_delete_posts(self, request, queryset):
        """Soft delete selected posts."""
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'{updated} posts were soft deleted.')
    soft_delete_posts.short_description = 'Soft delete selected posts'
    
    def restore_posts(self, request, queryset):
        """Restore soft deleted posts."""
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f'{updated} posts were restored.')
    restore_posts.short_description = 'Restore selected posts'
    
    def mark_as_not_reported(self, request, queryset):
        """Mark posts as not reported."""
        updated = queryset.update(is_reported=False)
        self.message_user(request, f'{updated} posts marked as not reported.')
    mark_as_not_reported.short_description = 'Mark as not reported'
    
    def get_queryset(self, request):
        """Optimize queryset with related objects."""
        return super().get_queryset(request).select_related(
            'author', 'custom_visibility_rule'
        )


@admin.register(PostVisibilityRule)
class PostVisibilityRuleAdmin(admin.ModelAdmin):
    """Admin interface for PostVisibilityRule model."""
    
    list_display = [
        'name', 'description_preview', 'criteria_summary',
        'is_active', 'eligible_users_count', 'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at', 'eligible_users_count']
    raw_id_fields = ['created_by']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Visibility Criteria', {
            'fields': (
                'caste_criteria', 'religion_criteria',
                'family_name_criteria', 'area_criteria'
            ),
            'description': 'Users must match ALL selected field groups (AND logic). '
                          'Within each field, values use OR logic.'
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at', 'updated_at', 'eligible_users_count'),
            'classes': ('collapse',)
        })
    )
    
    def description_preview(self, obj):
        """Display shortened description."""
        if len(obj.description) > 100:
            return obj.description[:100] + '...'
        return obj.description or '-'
    description_preview.short_description = 'Description'
    
    def criteria_summary(self, obj):
        """Display summary of criteria."""
        criteria = []
        
        if obj.caste_criteria:
            criteria.append(f'Caste: {len(obj.caste_criteria)} values')
        if obj.religion_criteria:
            criteria.append(f'Religion: {len(obj.religion_criteria)} values')
        if obj.family_name_criteria:
            criteria.append(f'Family: {len(obj.family_name_criteria)} values')
        if obj.area_criteria:
            criteria.append(f'Area: {len(obj.area_criteria)} values')
        
        return ', '.join(criteria) if criteria else 'No criteria'
    criteria_summary.short_description = 'Criteria'
    
    def eligible_users_count(self, obj):
        """Display count of eligible users."""
        try:
            count = obj.get_eligible_users_queryset().count()
            return f'{count:,} users'
        except:
            return 'Error calculating'
    eligible_users_count.short_description = 'Eligible Users'
    
    def get_queryset(self, request):
        """Optimize queryset with related objects."""
        return super().get_queryset(request).select_related('created_by')


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    """Admin interface for PostMedia model."""
    
    list_display = [
        'id', 'post_info', 'media_type', 'original_filename',
        'file_size_formatted', 'created_at'
    ]
    list_filter = ['media_type', 'created_at']
    search_fields = ['original_filename', 'post__content']
    readonly_fields = ['id', 'file_size', 'mime_type', 'created_at']
    raw_id_fields = ['post']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def file_size_formatted(self, obj):
        """Display file size in human readable format."""
        size = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    file_size_formatted.short_description = 'File Size'


@admin.register(PostComment)
class PostCommentAdmin(admin.ModelAdmin):
    """Admin interface for PostComment model."""
    
    list_display = [
        'id', 'post_info', 'author_info', 'content_preview',
        'is_deleted', 'is_edited', 'created_at'
    ]
    list_filter = ['is_deleted', 'is_edited', 'created_at']
    search_fields = ['content', 'author__mobile_number', 'post__content']
    readonly_fields = ['id', 'created_at', 'updated_at', 'edited_at']
    raw_id_fields = ['post', 'author', 'parent']
    
    actions = ['soft_delete_comments', 'restore_comments']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def author_info(self, obj):
        """Display author information with link."""
        if obj.author:
            url = reverse('admin:accounts_user_change', args=[obj.author.id])
            return format_html('<a href="{}">{}</a>', url, obj.author.mobile_number)
        return '-'
    author_info.short_description = 'Author'
    
    def content_preview(self, obj):
        """Display shortened content."""
        if len(obj.content) > 100:
            return obj.content[:100] + '...'
        return obj.content
    content_preview.short_description = 'Content'
    
    def soft_delete_comments(self, request, queryset):
        """Soft delete selected comments."""
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f'{updated} comments were soft deleted.')
    soft_delete_comments.short_description = 'Soft delete selected comments'
    
    def restore_comments(self, request, queryset):
        """Restore soft deleted comments."""
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f'{updated} comments were restored.')
    restore_comments.short_description = 'Restore selected comments'


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    """Admin interface for PostLike model."""
    
    list_display = ['id', 'post_info', 'user_info', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__mobile_number', 'post__content']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['post', 'user']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def user_info(self, obj):
        """Display user information with link."""
        if obj.user:
            url = reverse('admin:accounts_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.mobile_number)
        return '-'
    user_info.short_description = 'User'


@admin.register(PostShare)
class PostShareAdmin(admin.ModelAdmin):
    """Admin interface for PostShare model."""
    
    list_display = [
        'id', 'post_info', 'shared_by_info', 'share_platform',
        'is_active', 'created_at'
    ]
    list_filter = ['share_platform', 'is_active', 'created_at']
    search_fields = ['shared_by__mobile_number', 'post__content', 'share_text']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['post', 'shared_by']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def shared_by_info(self, obj):
        """Display sharer information with link."""
        if obj.shared_by:
            url = reverse('admin:accounts_user_change', args=[obj.shared_by.id])
            return format_html('<a href="{}">{}</a>', url, obj.shared_by.mobile_number)
        return '-'
    shared_by_info.short_description = 'Shared By'


@admin.register(PostSave)
class PostSaveAdmin(admin.ModelAdmin):
    """Admin interface for PostSave model."""
    
    list_display = ['id', 'post_info', 'user_info', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__mobile_number', 'post__content']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['post', 'user']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def user_info(self, obj):
        """Display user information with link."""
        if obj.user:
            url = reverse('admin:accounts_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.mobile_number)
        return '-'
    user_info.short_description = 'User'


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    """Admin interface for PostReport model."""
    
    list_display = [
        'id', 'post_info', 'reported_by_info', 'reason',
        'is_reviewed', 'is_action_taken', 'created_at'
    ]
    list_filter = [
        'reason', 'is_reviewed', 'is_action_taken', 'created_at'
    ]
    search_fields = [
        'reported_by__mobile_number', 'post__content', 'description'
    ]
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['post', 'reported_by', 'reviewed_by']
    
    actions = ['mark_as_reviewed', 'take_action']
    
    fieldsets = (
        ('Report Information', {
            'fields': ('post', 'reported_by', 'reason', 'description')
        }),
        ('Admin Action', {
            'fields': (
                'is_reviewed', 'is_action_taken', 'admin_notes',
                'reviewed_by', 'reviewed_at'
            )
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def reported_by_info(self, obj):
        """Display reporter information with link."""
        if obj.reported_by:
            url = reverse('admin:accounts_user_change', args=[obj.reported_by.id])
            return format_html('<a href="{}">{}</a>', url, obj.reported_by.mobile_number)
        return '-'
    reported_by_info.short_description = 'Reported By'
    
    def mark_as_reviewed(self, request, queryset):
        """Mark reports as reviewed."""
        updated = queryset.update(is_reviewed=True)
        self.message_user(request, f'{updated} reports marked as reviewed.')
    mark_as_reviewed.short_description = 'Mark as reviewed'
    
    def take_action(self, request, queryset):
        """Take action on reports."""
        updated = queryset.update(is_reviewed=True, is_action_taken=True)
        self.message_user(request, f'Action taken on {updated} reports.')
    take_action.short_description = 'Take action on reports'


@admin.register(PostAudience)
class PostAudienceAdmin(admin.ModelAdmin):
    """Admin interface for PostAudience model (for debugging)."""
    
    list_display = ['id', 'post_info', 'user_info', 'visibility_reason', 'created_at']
    list_filter = ['visibility_reason', 'created_at']
    search_fields = ['user__mobile_number', 'post__content']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['post', 'user']
    
    def post_info(self, obj):
        """Display post information with link."""
        if obj.post:
            url = reverse('admin:posts_post_change', args=[obj.post.id])
            return format_html(
                '<a href="{}">Post #{} - {}</a>',
                url, obj.post.id, obj.post.content[:50]
            )
        return '-'
    post_info.short_description = 'Post'
    
    def user_info(self, obj):
        """Display user information with link."""
        if obj.user:
            url = reverse('admin:accounts_user_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.mobile_number)
        return '-'
    user_info.short_description = 'User'


# Customize admin site headers
admin.site.site_header = 'Post System Administration'
admin.site.site_title = 'Post Admin'
admin.site.index_title = 'Welcome to Post System Admin'
