from rest_framework import serializers
from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for notifications"""
    
    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message', 'priority',
            'is_read', 'read_at', 'created_at', 'expires_at',
            'extra_data', 'content_type', 'object_id'
        ]
        read_only_fields = ['id', 'created_at', 'read_at']
    
    def get_icon(self, obj):
        """Get icon for notification type"""
        return obj.get_icon()


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for notification preferences"""
    
    class Meta:
        model = NotificationPreference
        fields = [
            'enable_websocket', 'enable_email', 'enable_sms',
            'event_notifications', 'post_notifications', 
            'family_notifications', 'system_notifications',
            'quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end',
            'daily_digest', 'weekly_digest'
        ]


class NotificationCreateSerializer(serializers.Serializer):
    """Serializer for creating notifications (admin use)"""
    user_id = serializers.IntegerField()
    notification_type = serializers.ChoiceField(choices=Notification.NOTIFICATION_TYPES)
    title = serializers.CharField(max_length=200)
    message = serializers.CharField()
    priority = serializers.ChoiceField(
        choices=Notification.PRIORITY_LEVELS,
        default='medium'
    )
    expires_at = serializers.DateTimeField(required=False)
