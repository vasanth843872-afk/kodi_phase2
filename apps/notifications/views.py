from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q

from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer, NotificationCreateSerializer
from .services import NotificationService


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for managing notifications"""
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    
    def get_queryset(self):
        """Get notifications for current user"""
        queryset = Notification.objects.filter(user=self.request.user)
        
        # Filter out expired notifications
        queryset = queryset.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        )
        
        # Filter by read status if requested
        read_status = self.request.query_params.get('read_status')
        if read_status == 'read':
            queryset = queryset.filter(is_read=True)
        elif read_status == 'unread':
            queryset = queryset.filter(is_read=False)
        
        # Filter by type if requested
        notification_type = self.request.query_params.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        return queryset.order_by('-created_at')
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read"""
        NotificationService.mark_all_as_read(request.user)
        return Response({'message': 'All notifications marked as read'})
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark specific notification as read"""
        notification = self.get_object()
        notification.mark_as_read()
        return Response({'message': 'Notification marked as read'})
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get unread notification count"""
        count = NotificationService.get_unread_count(request.user)
        return Response({'count': count})
    
    @action(detail=False, methods=['get', 'put'])
    def preferences(self, request):
        """Get or update notification preferences"""
        if request.method == 'GET':
            preferences, created = NotificationPreference.objects.get_or_create(
                user=request.user
            )
            serializer = NotificationPreferenceSerializer(preferences)
            return Response(serializer.data)
        
        elif request.method == 'PUT':
            preferences, created = NotificationPreference.objects.get_or_create(
                user=request.user
            )
            serializer = NotificationPreferenceSerializer(
                preferences, 
                data=request.data, 
                partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def cleanup_expired(self, request):
        """Clean up expired notifications (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        deleted_count = NotificationService.cleanup_expired_notifications()
        return Response({
            'message': f'Cleaned up {deleted_count} expired notifications'
        })
    
    @action(detail=False, methods=['post'])
    def create_notification(self, request):
        """Create notification (admin only)"""
        if not request.user.is_staff:
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = NotificationCreateSerializer(data=request.data)
        if serializer.is_valid():
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            try:
                user = User.objects.get(id=serializer.validated_data['user_id'])
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            notification = NotificationService.create_notification(
                user=user,
                notification_type=serializer.validated_data['notification_type'],
                title=serializer.validated_data['title'],
                message=serializer.validated_data['message'],
                priority=serializer.validated_data.get('priority', 'medium'),
                expires_at=serializer.validated_data.get('expires_at')
            )
            
            if notification:
                return Response(
                    NotificationSerializer(notification).data,
                    status=status.HTTP_201_CREATED
                )
            
            return Response(
                {'error': 'Failed to create notification'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
