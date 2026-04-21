import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.utils import timezone
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async
from django.db import models

from .models import Notification, NotificationPreference
from .services import NotificationService

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications
    """
    
    async def connect(self):
        """Connect user to their personal notification channel"""
        self.user = self.scope["user"]
        
        # Reject unauthenticated connections
        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Rejected unauthenticated notification WebSocket connection")
            await self.close(code=4001)
            return
        
        # Create unique room for this user
        self.room_group_name = f"user_{self.user.id}_notifications"
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to notification WebSocket")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to notification service',
            'user_id': self.user.id,
            'unread_count': await self.get_unread_count(),
            'timestamp': timezone.now().isoformat()
        }))
        
        # Send any pending notifications
        await self.send_pending_notifications()
    
    async def disconnect(self, close_code):
        """Leave room group"""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.id} disconnected from notification WebSocket")
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            handlers = {
                'get_notifications': self.handle_get_notifications,
                'mark_read': self.handle_mark_read,
                'mark_all_read': self.handle_mark_all_read,
                'get_unread_count': self.handle_get_unread_count,
                'ping': self.handle_ping,
                'get_preferences': self.handle_get_preferences,
                'update_preferences': self.handle_update_preferences,
            }
            
            handler = handlers.get(message_type)
            if handler:
                await handler(data)
            else:
                await self.send_error(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)
            await self.send_error(f"Internal error: {str(e)}")
    
    async def notification_message(self, event):
        """Handle new notification message"""
        notification = event['notification']
        
        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification': notification,
            'unread_count': await self.get_unread_count(),
            'timestamp': timezone.now().isoformat()
        }))
    
    async def handle_get_notifications(self, data):
        """Handle request for notifications"""
        page = data.get('page', 1)
        page_size = data.get('page_size', 20)
        unread_only = data.get('unread_only', False)
        
        notifications = await self.get_notifications(page, page_size, unread_only)
        
        await self.send(text_data=json.dumps({
            'type': 'notifications_list',
            'notifications': notifications,
            'page': page,
            'unread_count': await self.get_unread_count(),
        }))
    
    async def handle_mark_read(self, data):
        """Handle mark notification as read"""
        notification_id = data.get('notification_id')
        
        if notification_id:
            success = await self.mark_notification_read(notification_id)
            
            if success:
                await self.send(text_data=json.dumps({
                    'type': 'notification_marked_read',
                    'notification_id': notification_id,
                    'unread_count': await self.get_unread_count(),
                }))
            else:
                await self.send_error("Notification not found")
    
    async def handle_mark_all_read(self, data):
        """Handle mark all notifications as read"""
        await self.mark_all_notifications_read()
        
        await self.send(text_data=json.dumps({
            'type': 'all_notifications_marked_read',
            'unread_count': 0,
        }))
    
    async def handle_get_unread_count(self, data):
        """Handle request for unread count"""
        count = await self.get_unread_count()
        
        await self.send(text_data=json.dumps({
            'type': 'unread_count',
            'count': count,
        }))
    
    async def handle_ping(self, data):
        """Respond to ping to keep connection alive"""
        await self.send(text_data=json.dumps({
            'type': 'pong',
            'timestamp': timezone.now().isoformat()
        }))
    
    async def handle_get_preferences(self, data):
        """Handle request for notification preferences"""
        preferences = await self.get_user_preferences()
        
        await self.send(text_data=json.dumps({
            'type': 'notification_preferences',
            'preferences': preferences,
        }))
    
    async def handle_update_preferences(self, data):
        """Handle update notification preferences"""
        preferences_data = data.get('preferences', {})
        
        success = await self.update_user_preferences(preferences_data)
        
        if success:
            await self.send(text_data=json.dumps({
                'type': 'preferences_updated',
                'preferences': await self.get_user_preferences(),
            }))
        else:
            await self.send_error("Failed to update preferences")
    
    async def send_pending_notifications(self):
        """Send any pending unread notifications"""
        notifications = await self.get_notifications(page=1, page_size=10, unread_only=True)
        
        if notifications:
            await self.send(text_data=json.dumps({
                'type': 'pending_notifications',
                'notifications': notifications,
                'unread_count': await self.get_unread_count(),
            }))
    
    @sync_to_async
    def get_notifications(self, page=1, page_size=20, unread_only=False):
        """Get notifications for user"""
        queryset = Notification.objects.filter(user=self.user)
        
        if unread_only:
            queryset = queryset.filter(is_read=False)
        
        # Filter out expired notifications
        queryset = queryset.filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )
        
        notifications = queryset.order_by('-created_at')[
            (page - 1) * page_size:page * page_size
        ]
        
        return [
            {
                'id': notif.id,
                'type': notif.notification_type,
                'title': notif.title,
                'message': notif.message,
                'priority': notif.priority,
                'icon': notif.get_icon(),
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'extra_data': notif.extra_data,
            }
            for notif in notifications
        ]
    
    @sync_to_async
    def get_unread_count(self):
        """Get unread notification count"""
        return NotificationService.get_unread_count(self.user)
    
    @sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark specific notification as read"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False
    
    @sync_to_async
    def mark_all_notifications_read(self):
        """Mark all notifications as read"""
        NotificationService.mark_all_as_read(self.user)
    
    @sync_to_async
    def get_user_preferences(self):
        """Get user notification preferences"""
        preferences, created = NotificationPreference.objects.get_or_create(
            user=self.user,
            defaults={
                'enable_websocket': True,
                'enable_email': True,
                'enable_sms': False,
                'event_notifications': True,
                'post_notifications': True,
                'family_notifications': True,
                'system_notifications': True,
            }
        )
        
        return {
            'enable_websocket': preferences.enable_websocket,
            'enable_email': preferences.enable_email,
            'enable_sms': preferences.enable_sms,
            'event_notifications': preferences.event_notifications,
            'post_notifications': preferences.post_notifications,
            'family_notifications': preferences.family_notifications,
            'system_notifications': preferences.system_notifications,
            'quiet_hours_enabled': preferences.quiet_hours_enabled,
            'quiet_hours_start': preferences.quiet_hours_start.isoformat() if preferences.quiet_hours_start else None,
            'quiet_hours_end': preferences.quiet_hours_end.isoformat() if preferences.quiet_hours_end else None,
            'daily_digest': preferences.daily_digest,
            'weekly_digest': preferences.weekly_digest,
        }
    
    @sync_to_async
    def update_user_preferences(self, preferences_data):
        """Update user notification preferences"""
        try:
            preferences, created = NotificationPreference.objects.get_or_create(
                user=self.user
            )
            
            # Update preferences
            for key, value in preferences_data.items():
                if hasattr(preferences, key):
                    setattr(preferences, key, value)
            
            preferences.save()
            return True
        except Exception as e:
            logger.error(f"Failed to update preferences: {str(e)}")
            return False
    
    async def send_error(self, message):
        """Send error message to client"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        ))
