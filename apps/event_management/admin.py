from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Event, EventType, VisibilityLevel, EventConfig,
    RSVP, EventMedia, EventComment, EventFlag, UserRestriction
)
from apps.notifications.services import NotificationService, get_user_display_name

@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'usage_count', 'is_public', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['title', 'created_by__username']
    readonly_fields = ['usage_count', 'last_used', 'created_at', 'updated_at']


@admin.register(VisibilityLevel)
class VisibilityLevelAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_enabled', 'is_default', 'sort_order']
    list_filter = ['is_enabled', 'is_default']
    list_editable = ['is_enabled', 'is_default', 'sort_order']


@admin.register(EventConfig)
class EventConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Basic Settings', {
            'fields': ('default_visibility', 'allow_users_change_visibility', 'max_allowed_visibility')
        }),
        ('Auto-Filters', {
            'fields': (
                'enable_lifestyle_filter', 'enable_familyname8_filter',
                'enable_family_filter', 'enable_location_filter',
                'enable_connection_filter'
            )
        }),
        ('Block Lists', {
            'fields': ('blocked_lifestyles', 'blocked_familyname8s', 'blocked_families', 'blocked_locations')
        }),
        ('Moderation', {
            'fields': ('require_moderation', 'auto_approve_trusted_users')
        }),
        ('Audit', {
            'fields': ('updated_by', 'updated_at')
        }),
    )
    readonly_fields = ['updated_at']
    
    def has_add_permission(self, request):
        return not EventConfig.objects.exists()


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'event_type', 'start_date', 'city',
        'created_by', 'visibility', 'status', 'rsvp_going'
    ]
    list_filter = ['status', 'visibility', 'is_virtual', 'city', 'state']
    search_fields = ['title', 'description', 'location_name']
    date_hierarchy = 'start_date'
    readonly_fields = [
        'view_count', 'rsvp_going', 'rsvp_maybe', 'rsvp_not_going',
        'created_at', 'updated_at'
    ]
    filter_horizontal = ['honorees', 'invited_users', 'invited_persons', 'excluded_users']
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('title', 'description', 'event_type')
        }),
        ('Date & Location', {
            'fields': (
                'start_date', 'end_date', 'is_all_day', 'timezone',
                'location_name', 'address', 'city', 'state', 'country',
                'is_virtual', 'virtual_link'
            )
        }),
        ('People', {
            'fields': ('created_by', 'honorees')
        }),
        ('Visibility', {
            'fields': (
                'visibility', 'target_lifestyles', 'target_familyname8s',
                'target_families', 'target_locations', 'invited_users',
                'invited_persons', 'excluded_users'
            )
        }),
        ('Moderation', {
            'fields': ('status', 'moderation_note', 'moderated_by', 'moderated_at')
        }),
        ('Media', {
            'fields': ('cover_image',)
        }),
        ('Stats', {
            'fields': ('view_count', 'rsvp_going', 'rsvp_maybe', 'rsvp_not_going')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    actions = ['approve_events', 'reject_events', 'make_public']
    
    def approve_events(self, request, queryset):
        for event in queryset:
            old_status = event.status
            event.status = 'APPROVED'
            event.moderated_by = request.user
            event.moderated_at = timezone.now()
            event.save()
            
            # Send notification to event creator
            if old_status != 'APPROVED':
                NotificationService.create_event_notification(
                    event=event,
                    notification_type='event_updated',
                    users=[event.created_by],
                    message=f"Admin {get_user_display_name(request.user)} approved your event '{event.title}'",
                    actor=request.user
                )
    approve_events.short_description = "Approve selected events"
    
    def reject_events(self, request, queryset):
        for event in queryset:
            event.status = 'REJECTED'
            event.moderated_by = request.user
            event.moderated_at = timezone.now()
            event.save()
            
            # Send notification to event creator
            NotificationService.create_event_notification(
                event=event,
                notification_type='event_updated',
                users=[event.created_by],
                message=f"Admin {get_user_display_name(request.user)} rejected your event '{event.title}'",
                actor=request.user
            )
    reject_events.short_description = "Reject selected events"
    
    def make_public(self, request, queryset):
        public = VisibilityLevel.objects.get(code='PUBLIC')
        for event in queryset:
            old_visibility = event.visibility
            event.visibility = public
            event.save()
            
            # Send notification to event creator if visibility changed
            if old_visibility != public:
                NotificationService.create_event_notification(
                    event=event,
                    notification_type='event_updated',
                    users=[event.created_by],
                    message=f"Admin {get_user_display_name(request.user)} made your event '{event.title}' public",
                    actor=request.user
                )
    make_public.short_description = "Make selected events public"


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = ['event', 'user', 'response', 'guests_count', 'created_at']
    list_filter = ['response']
    search_fields = ['event__title', 'user__username']
    date_hierarchy = 'created_at'


@admin.register(EventMedia)
class EventMediaAdmin(admin.ModelAdmin):
    list_display = ['event', 'media_type', 'uploaded_by', 'uploaded_at']
    list_filter = ['media_type']
    search_fields = ['event__title', 'caption']
    filter_horizontal = ['tagged_persons']


@admin.register(EventComment)
class EventCommentAdmin(admin.ModelAdmin):
    list_display = ['event', 'user', 'content_preview', 'is_approved', 'is_flagged', 'created_at']
    list_filter = ['is_approved', 'is_flagged']
    search_fields = ['content', 'event__title', 'user__username']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Comment'
    
    actions = ['approve_comments', 'reject_comments']
    
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = "Approve selected comments"
    
    def reject_comments(self, request, queryset):
        queryset.update(is_approved=False)
    reject_comments.short_description = "Reject selected comments"


@admin.register(EventFlag)
class EventFlagAdmin(admin.ModelAdmin):
    list_display = ['event', 'reported_by', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason']
    search_fields = ['event__title', 'reported_by__username']
    date_hierarchy = 'created_at'
    
    actions = ['resolve_flags', 'dismiss_flags']
    
    def resolve_flags(self, request, queryset):
        queryset.update(
            status='RESOLVED',
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
    resolve_flags.short_description = "Resolve selected flags"
    
    def dismiss_flags(self, request, queryset):
        queryset.update(
            status='DISMISSED',
            resolved_by=request.user,
            resolved_at=timezone.now()
        )
    dismiss_flags.short_description = "Dismiss selected flags"


@admin.register(UserRestriction)
class UserRestrictionAdmin(admin.ModelAdmin):
    list_display = ['user', 'can_create_events', 'max_visibility', 'created_at']
    list_filter = ['can_create_events']
    search_fields = ['user__username']
    filter_horizontal = ['restricted_to_visibility']
    readonly_fields = ['created_at', 'updated_at']