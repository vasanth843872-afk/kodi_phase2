from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
import logging
from .models import Notification, NotificationPreference
logger = logging.getLogger(__name__)


def get_user_display_name(user):
    """Get user's display name from profile, fallback to mobile number"""
    try:
        profile = user.profile
        if profile.firstname:
            return profile.firstname
    except AttributeError:
        pass
    return user.mobile_number
User = get_user_model()

class NotificationService:
    """Service for creating and managing notifications"""
    
    @staticmethod
    def create_notification(
        user,
        notification_type,
        title,
        message,
        priority='medium',
        content_object=None,
        extra_data=None,
        expires_at=None
    ):
        """Create a new notification"""
        try:
            notification = Notification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
                extra_data=extra_data or {},
                expires_at=expires_at
            )
            
            # Set content object if provided
            if content_object:
                notification.content_type = ContentType.objects.get_for_model(content_object)
                notification.object_id = content_object.id
                notification.save(update_fields=['content_type', 'object_id'])
            
            # Send notification based on user preferences
            NotificationService._send_notification(notification)
            
            return notification
            
        except Exception as e:
            logger.error(f"Failed to create notification: {str(e)}")
            return None
    
    @staticmethod
    def _send_notification(notification):
        """Send notification based on user preferences"""
        try:
            user = notification.user
            
            # Get or create user preferences
            preferences, created = NotificationPreference.objects.get_or_create(
                user=user,
                defaults={
                    'enable_websocket': True,
                    'enable_email': True,
                    'enable_sms': False,
                }
            )
            
            # Check if we should send during quiet hours
            if preferences.is_quiet_hours():
                # Only send urgent notifications during quiet hours
                if notification.priority != 'urgent':
                    return
            
            # Send WebSocket notification
            if preferences.enable_websocket:
                NotificationService._send_websocket_notification(notification)
            
            # Send email notification (for high priority or if user prefers)
            if preferences.enable_email and notification.priority in ['high', 'urgent']:
                NotificationService._send_email_notification(notification)
            
            # Send SMS notification (for urgent only)
            if preferences.enable_sms and notification.priority == 'urgent':
                NotificationService._send_sms_notification(notification)
                
        except Exception as e:
            logger.error(f"Failed to send notification {notification.id}: {str(e)}")
    
    @staticmethod
    def _send_websocket_notification(notification):
        """Send notification via WebSocket"""
        try:
            channel_layer = get_channel_layer()
            
            notification_data = {
                'type': 'notification',
                'id': notification.id,
                'notification_type': notification.notification_type,
                'title': notification.title,
                'message': notification.message,
                'priority': notification.priority,
                'icon': notification.get_icon(),
                'created_at': notification.created_at.isoformat(),
                'extra_data': notification.extra_data,
            }
            
            # Add content object info if available
            if notification.content_object:
                notification_data['content_object'] = {
                    'type': notification.content_type.model,
                    'id': notification.object_id,
                }
            
            async_to_sync(channel_layer.group_send)(
                f"user_{notification.user.id}_notifications",
                {
                    'type': 'notification_message',
                    'notification': notification_data
                }
            )
            
            # Mark as sent via WebSocket
            notification.sent_via_websocket = True
            notification.save(update_fields=['sent_via_websocket'])
            
            logger.info(f"WebSocket notification sent to user {notification.user.id}")
            
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {str(e)}")
    
    @staticmethod
    def _send_email_notification(notification):
        """Send notification via email"""
        try:
            # TODO: Implement email sending logic
            # This would integrate with your email service
            notification.sent_via_email = True
            notification.save(update_fields=['sent_via_email'])
            logger.info(f"Email notification sent to user {notification.user.id}")
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")
    
    @staticmethod
    def _send_sms_notification(notification):
        """Send notification via SMS"""
        try:
            # TODO: Implement SMS sending logic
            # This would integrate with your SMS service
            notification.sent_via_sms = True
            notification.save(update_fields=['sent_via_sms'])
            logger.info(f"SMS notification sent to user {notification.user.id}")
        except Exception as e:
            logger.error(f"Failed to send SMS notification: {str(e)}")
    
    @staticmethod
    def create_event_notification(event, notification_type, users=None, message=None, actor=None):
        """Create event-related notifications"""
        print(f"DEBUG: create_event_notification called")
        print(f"DEBUG: event={event.id} - {event.title}")
        print(f"DEBUG: notification_type={notification_type}")
        print(f"DEBUG: users={users}")
        print(f"DEBUG: actor={actor}")
        
        if users is None:
            users = []
        
        # Get actor display name for message
        actor_name = get_user_display_name(actor) if actor else "Admin"
        print(f"DEBUG: actor_name={actor_name}")
        
        if message is None:
            message = f"Event {event.title}"
        
        print(f"DEBUG: message={message}")
        
        title_map = {
            'event_created': f'New Event: {event.title}',
            'event_updated': f'Event Updated: {event.title}',
            'event_cancelled': f'Event Cancelled: {event.title}',
            'event_reminder': f'Reminder: {event.title}',
            'event_starting_soon': f'Event Starting Soon: {event.title}',
            'event_ended': f'Event Ended: {event.title}',
            'rsvp_received': f'RSVP for {event.title}',
            'rsvp_updated': f'RSVP Updated for {event.title}',
            'event_comment': f'New comment on {event.title}',
            'event_media_added': f'New media for {event.title}',
        }
        
        title = title_map.get(notification_type, f'Event: {event.title}')
        print(f"DEBUG: title={title}")
        
        notifications = []
        for user in users:
            print(f"DEBUG: Creating notification for user {user}")
            try:
                notification = NotificationService.create_notification(
                    user=user,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    content_object=event,
                    extra_data={
                        'event_id': event.id,
                        'event_title': event.title,
                        'start_date': event.start_date.isoformat() if event.start_date else None,
                        'actor_name': actor_name,
                    }
                )
                if notification:
                    notifications.append(notification)
                    print(f"DEBUG: Notification created successfully for user {user} - ID: {notification.id}")
                else:
                    print(f"DEBUG: Failed to create notification for user {user}")
            except Exception as e:
                print(f"DEBUG: Error creating notification for user {user}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"DEBUG: Returning {len(notifications)} notifications")
        return notifications
    
    @staticmethod
    def create_post_notification(post, notification_type, users=None, message=None, actor=None):
        """Create post-related notifications"""
        if users is None:
            users = []
        
        # Get actor display name for message
        actor_name = get_user_display_name(actor) if actor else get_user_display_name(post.author)
        
        if message is None:
            message = f"Post by {actor_name}"
        
        title_map = {
            'post_created': f'New Post by {actor_name}',
            'post_updated': f'Post Updated by {actor_name}',
            'post_liked': f'Your post was liked',
            'post_commented': f'New comment on your post',
            'post_shared': f'Your post was shared',
            'post_mentioned': f'You were mentioned in a post',
            'post_reported': f'A post was reported',
        }
        
        title = title_map.get(notification_type, f'Post: {post.content[:50]}')
        
        notifications = []
        for user in users:
            notification = NotificationService.create_notification(
                user=user,
                notification_type=notification_type,
                title=title,
                message=message,
                content_object=post,
                extra_data={
                    'post_id': post.id,
                    'author_id': post.author.id,
                    'author_mobile': post.author.mobile_number,
                    'author_name': get_user_display_name(post.author),
                    'content_preview': post.content[:100],
                }
            )
            if notification:
                notifications.append(notification)
        
        return notifications
    
    @staticmethod
    def get_unread_count(user):
        """Get unread notification count for user"""
        return Notification.objects.filter(user=user, is_read=False).count()
    
    @staticmethod
    def mark_all_as_read(user):
        """Mark all notifications as read for user"""
        Notification.objects.filter(user=user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
    
    @staticmethod
    def cleanup_expired_notifications():
        """Delete expired notifications"""
        expired_count = Notification.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()[0]
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired notifications")
        
        return expired_count
