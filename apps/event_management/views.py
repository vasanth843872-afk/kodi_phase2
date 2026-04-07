from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from apps.genealogy.models import PersonRelation,Person

from .models import (
    Event, EventType, VisibilityLevel, RSVP, 
    EventMedia, EventComment, EventFlag, EventConfig,
    UserRestriction
)
from .serializers import (
    EventListSerializer, EventDetailSerializer, EventCreateUpdateSerializer,
    EventTypeSerializer, EventTypeCreateSerializer,
    VisibilityLevelSerializer, RSVPSerializer,
    EventMediaSerializer, EventCommentSerializer, EventFlagSerializer,
    EventConfigSerializer
)
from .permissions import (
    CanCreateEvent, CanViewEvent, IsEventCreatorOrAdmin,
    IsAdminOrModerator, CanCreateEventType
)
from .filters import EventFilter


# ==================== EVENT TYPE VIEWS ====================

class EventTypeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for event types - anyone can create
    """
    permission_classes = [IsAuthenticated, CanCreateEventType]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['start_date', 'end_date', 'created_at', 'view_count']
    
    
    def get_queryset(self):
        user = self.request.user
        
        # Show relevant event types:
        # 1. Public types
        # 2. User's own types
        # 3. Family types (if user belongs to that family)
        queryset = EventType.objects.filter(
            Q(is_public=True) |
            Q(created_by=user) |
            Q(family__persons__linked_user=user)
        ).distinct()
        
        # Order by usage
        return queryset.order_by('-usage_count', 'title')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return EventTypeCreateSerializer
        return EventTypeSerializer
    
    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Get most used event types"""
        types = self.get_queryset().order_by('-usage_count')[:20]
        serializer = self.get_serializer(types, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_types(self, request):
        """Get event types created by current user"""
        types = self.get_queryset().filter(created_by=request.user)
        serializer = self.get_serializer(types, many=True)
        return Response(serializer.data)


# ==================== EVENT VIEWS ====================

class EventViewSet(viewsets.ModelViewSet):
    """
    Main Event ViewSet
    """
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = EventFilter
    search_fields = ['title', 'description', 'location_name', 'city']
    ordering_fields = ['start_date', 'created_at', 'view_count']
    ordering = ['start_date']
    
    def get_queryset(self):
        queryset = Event.objects.all()
        user = self.request.user
        
        # Admin sees everything
        if user.is_staff:
            return queryset.select_related(
                'event_type', 'created_by', 'visibility'
            ).prefetch_related('honorees')
        
        # Get user's person record
        try:
            user_person = user.person_record
        except Person.DoesNotExist:
            # If no person record, only show approved events
            return queryset.filter(status='APPROVED').select_related(
                'event_type', 'created_by', 'visibility'
            ).prefetch_related('honorees')
        
        # Get IDs of all people connected to this user
        # via confirmed relations
        connected_person_ids = []
        
        # People this user is connected TO (outgoing)
        outgoing_connections = PersonRelation.objects.filter(
            from_person=user_person,
            status='confirmed'
        ).values_list('to_person_id', flat=True)
        
        # People connected TO this user (incoming)
        incoming_connections = PersonRelation.objects.filter(
            to_person=user_person,
            status='confirmed'
        ).values_list('from_person_id', flat=True)
        
        # Combine all connected person IDs
        connected_person_ids = list(outgoing_connections) + list(incoming_connections)
        
        # Get all users linked to these connected persons
        connected_user_ids = Person.objects.filter(
            id__in=connected_person_ids,
            linked_user__isnull=False
        ).values_list('linked_user_id', flat=True)
        
        # Now filter events:
        # 1. All APPROVED events
        # 2. PENDING events with CONNECTED visibility from connected users
        queryset = queryset.filter(
            Q(status='APPROVED') |
            Q(
                status='PENDING',
                visibility__code='CONNECTED',
                created_by_id__in=connected_user_ids
            )
        ).distinct()
        
        return queryset.select_related(
            'event_type', 'created_by', 'visibility'
        ).prefetch_related('honorees')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return EventListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return EventCreateUpdateSerializer
        return EventDetailSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            permission_classes = [IsAuthenticated, CanCreateEvent]
        elif self.action in ['update', 'partial_update', 'destroy']:
            permission_classes = [IsAuthenticated, IsEventCreatorOrAdmin]
        elif self.action in ['moderate', 'pending', 'flagged', 'config']:
            permission_classes = [IsAuthenticated, IsAdminOrModerator]
        else:
            permission_classes = [IsAuthenticated, CanViewEvent]
        return [p() for p in permission_classes]
    
    def retrieve(self, request, *args, **kwargs):
        """Increment view count on retrieve"""
        instance = self.get_object()
        instance.view_count += 1
        instance.save(update_fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    # ========== RSVP ACTIONS ==========
    
    @action(detail=True, methods=['post'])
    def rsvp(self, request, pk=None):
        """RSVP to an event"""
        event = self.get_object()
        
        serializer = RSVPSerializer(
            data=request.data,
            context={'request': request, 'event': event}
        )
        
        if serializer.is_valid():
            rsvp, created = RSVP.objects.update_or_create(
                event=event,
                user=request.user,
                defaults=serializer.validated_data
            )
            
            return Response({
                'status': 'success',
                'message': f'RSVP updated to {rsvp.response}',
                'response': rsvp.response
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def rsvp_list(self, request, pk=None):
        """Get all RSVPs for an event"""
        event = self.get_object()
        
        # Only creator and admin can see full list
        if not (request.user.is_staff or event.created_by == request.user):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        response_filter = request.query_params.get('response')
        rsvps = event.rsvps.all()
        
        if response_filter:
            rsvps = rsvps.filter(response=response_filter)
        
        serializer = RSVPSerializer(rsvps, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['delete'])
    def cancel_rsvp(self, request, pk=None):
        """Cancel RSVP"""
        event = self.get_object()
        
        try:
            rsvp = event.rsvps.get(user=request.user)
            rsvp.delete()
            return Response({'status': 'RSVP cancelled'})
        except RSVP.DoesNotExist:
            return Response(
                {'error': 'No RSVP found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # ========== MEDIA ACTIONS ==========
    
    @action(detail=True, methods=['post'])
    def add_media(self, request, pk=None):
        """Add media to event"""
        event = self.get_object()
        
        # Check permission
        if not (request.user.is_staff or event.created_by == request.user):
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = EventMediaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                event=event,
                uploaded_by=request.user
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def media(self, request, pk=None):
        """Get all media for an event"""
        event = self.get_object()
        media = event.media.all()
        serializer = EventMediaSerializer(media, many=True)
        return Response(serializer.data)
    
    # ========== COMMENT ACTIONS ==========
    
    @action(detail=True, methods=['post'])
    def comment(self, request, pk=None):
        """Add comment to event"""
        event = self.get_object()
        
        serializer = EventCommentSerializer(
            data=request.data,
            context={'request': request, 'event': event}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def comments(self, request, pk=None):
        """Get comments for an event"""
        event = self.get_object()
        comments = event.comments.filter(
            parent=None, is_approved=True
        ).order_by('created_at')
        
        serializer = EventCommentSerializer(comments, many=True)
        return Response(serializer.data)
    
    # ========== FLAG ACTIONS ==========
    
    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        """Flag event as inappropriate"""
        event = self.get_object()
        
        # Check if already flagged by this user
        if EventFlag.objects.filter(event=event, reported_by=request.user).exists():
            return Response(
                {'error': 'You have already flagged this event'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = EventFlagSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                event=event,
                reported_by=request.user
            )
            
            # Update event status
            if event.status == 'APPROVED':
                event.status = 'FLAGGED'
                event.save(update_fields=['status'])
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrModerator])
    def flags(self, request, pk=None):
        """Get all flags for a specific event with reasons (Admin only)"""
        event = self.get_object()
        flags = event.flags.all().order_by('-created_at')
        
        # Group by reason for statistics
        reason_counts = {}
        for reason_code, reason_label in EventFlag.REASON_CHOICES:
            count = flags.filter(reason=reason_code).count()
            if count > 0:
                reason_counts[reason_label] = count
        
        serializer = EventFlagSerializer(flags, many=True)
        
        return Response({
            'event_id': event.id,
            'event_title': event.title,
            'event_status': event.status,
            'total_flags': flags.count(),
            'reason_breakdown': reason_counts,  # This shows counts by reason
            'flags': serializer.data
        })
    # ========== FILTERED LISTS ==========
    
    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming events"""
        events = self.get_queryset().filter(
            start_date__gte=timezone.now(),
            status='APPROVED'
        ).order_by('start_date')[:50]
        
        # Filter by visibility
        visible_events = [e for e in events if e.is_visible_to(request.user)]
        
        serializer = EventListSerializer(
            visible_events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def past(self, request):
        """Get past events"""
        events = self.get_queryset().filter(
            start_date__lt=timezone.now(),
            status='APPROVED'
        ).order_by('-start_date')[:50]
        
        # Filter by visibility
        visible_events = [e for e in events if e.is_visible_to(request.user)]
        
        serializer = EventListSerializer(
            visible_events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_events(self, request):
        """Get events I created"""
        events = self.get_queryset().filter(created_by=request.user)
        serializer = EventListSerializer(
            events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def my_comment_replies(self, request):
        """Get all replies to comments made by current user"""
        # Get all comments made by current user
        my_comments = EventComment.objects.filter(user=request.user)
        
        # Get replies to those comments
        replies = EventComment.objects.filter(
            parent__in=my_comments
        ).select_related('user', 'parent').order_by('-created_at')
        
        serializer = EventCommentSerializer(replies, many=True)
        return Response({
            'count': replies.count(),
            'replies': serializer.data
        })
    
    
    @action(detail=True, methods=['get', 'put', 'patch', 'delete'], url_path='comments/(?P<comment_id>[^/.]+)')
    def comment_detail(self, request, pk=None, comment_id=None):
        """
        Retrieve, update or delete a comment/reply
        GET: Get specific comment
        PUT: Update entire comment
        PATCH: Partially update comment
        DELETE: Delete comment
        """
        event = self.get_object()
        
        # Get the comment
        try:
            comment = event.comments.get(id=comment_id)
        except EventComment.DoesNotExist:
            return Response(
                {'error': 'Comment not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # GET - Retrieve comment
        if request.method == 'GET':
            serializer = EventCommentSerializer(comment)
            return Response(serializer.data)
        
        # Check permission for modifications (only comment author or admin)
        if request.method in ['PUT', 'PATCH', 'DELETE']:
            if not (request.user.is_staff or comment.user == request.user):
                return Response(
                    {'error': 'You can only modify your own comments'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # PUT/PATCH - Update comment
        if request.method in ['PUT', 'PATCH']:
            serializer = EventCommentSerializer(
                comment,
                data=request.data,
                partial=(request.method == 'PATCH'),
                context={'request': request}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # DELETE - Remove comment
        if request.method == 'DELETE':
            comment.delete()
            return Response(
                {'message': 'Comment deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
    
    @action(detail=False, methods=['get'])
    def my_rsvps(self, request):
        """Get events I've RSVP'd to"""
        events = Event.objects.filter(
            rsvps__user=request.user
        ).distinct()
        
        serializer = EventListSerializer(
            events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get events in calendar format"""
        year = request.query_params.get('year', timezone.now().year)
        month = request.query_params.get('month', timezone.now().month)
        
        start_date = timezone.datetime(int(year), int(month), 1)
        if month == 12:
            end_date = timezone.datetime(int(year)+1, 1, 1)
        else:
            end_date = timezone.datetime(int(year), int(month)+1, 1)
        
        events = self.get_queryset().filter(
            start_date__gte=start_date,
            start_date__lt=end_date,
            status='APPROVED'
        )
        
        # Filter by visibility
        calendar_data = []
        for event in events:
            if event.is_visible_to(request.user):
                calendar_data.append({
                    'id': event.id,
                    'title': event.title,
                    'start': event.start_date.isoformat(),
                    'end': event.end_date.isoformat() if event.end_date else None,
                    'allDay': event.is_all_day,
                    'color': event.visibility.color if event.visibility else '#3788d8'
                })
        
        return Response(calendar_data)
    
    # ========== ADMIN/MODERATOR ACTIONS ==========
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrModerator])
    def moderate(self, request, pk=None):
        """Approve or reject event"""
        event = self.get_object()
        
        action = request.data.get('action')
        note = request.data.get('note', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {'error': 'Action must be approve or reject'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action == 'approve':
            event.status = 'APPROVED'
            message = 'Event approved'
        else:
            event.status = 'REJECTED'
            message = 'Event rejected'
        
        event.moderation_note = note
        event.moderated_by = request.user
        event.moderated_at = timezone.now()
        event.save()
        
        return Response({'message': message})
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrModerator])
    def pending(self, request):
        """Get events pending moderation"""
        events = self.get_queryset().filter(status='PENDING')
        serializer = EventDetailSerializer(
            events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrModerator])
    def flagged(self, request):
        """Get flagged events"""
        events = self.get_queryset().filter(status='FLAGGED')
        serializer = EventDetailSerializer(
            events,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrModerator])
    def stats(self, request):
        """Get event statistics"""
        total = Event.objects.count()
        upcoming = Event.objects.filter(start_date__gte=timezone.now()).count()
        past = Event.objects.filter(start_date__lt=timezone.now()).count()
        
        by_status = dict(Event.objects.values_list('status').annotate(count=Count('id')))
        by_visibility = dict(Event.objects.values_list('visibility__code').annotate(count=Count('id')))
        
        return Response({
            'total_events': total,
            'upcoming': upcoming,
            'past': past,
            'by_status': by_status,
            'by_visibility': by_visibility,
            'total_rsvps': RSVP.objects.count(),
            'total_comments': EventComment.objects.count(),
            'total_media': EventMedia.objects.count(),
            'flagged_count': Event.objects.filter(status='FLAGGED').count()
        })


# ==================== VISIBILITY LEVEL VIEWS ====================

class VisibilityLevelViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for visibility levels"""
    queryset = VisibilityLevel.objects.filter(is_enabled=True)
    serializer_class = VisibilityLevelSerializer
    permission_classes = [IsAuthenticated]


# ==================== ADMIN CONFIG VIEWS ====================

class EventConfigViewSet(viewsets.ViewSet):
    """Admin configuration endpoints"""
    permission_classes = [IsAuthenticated, IsAdminOrModerator]
    
    @action(detail=False, methods=['get'])
    def get(self, request):
        """Get current config"""
        config = EventConfig.get_config()
        serializer = EventConfigSerializer(config)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def custom_update(self, request):
        """Update config"""
        config = EventConfig.get_config()
        serializer = EventConfigSerializer(config, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save(updated_by=request.user)
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=False, methods=['post'])
    def restrict_user(self, request):
            """Restrict a specific user"""
            user_id = request.data.get('user_id')
            if not user_id:
                return Response(
                    {'error': 'user_id required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            restriction, created = UserRestriction.objects.get_or_create(
                user=user,
                defaults={'created_by': request.user}
            )
            
            # Update fields
            fields = ['can_create_events', 'max_visibility', 'blocked_religions',
                    'blocked_castes', 'blocked_families', 'restriction_reason']
            
            for field in fields:
                if field in request.data:
                    setattr(restriction, field, request.data[field])
            
            if 'restricted_to_visibility' in request.data:
                visibility_ids = request.data['restricted_to_visibility']
                restriction.restricted_to_visibility.set(visibility_ids)
            
            restriction.save()
            
            # Get first name from profile
            first_name = "User"
            if hasattr(user, 'profile') and user.profile:
                first_name = user.profile.firstname or user.profile.first_name or "User"
            elif hasattr(user, 'first_name'):
                first_name = user.first_name
            elif hasattr(user, 'get_full_name'):
                first_name = user.get_full_name() or "User"
            
            return Response({'message': f'User {first_name} restricted successfully'})
        
    
    @action(detail=False, methods=['get'], permission_classes=[IsAdminOrModerator])
    def user_restrictions(self, request):
        user_id = request.query_params.get('user_id')
        try:
            restriction = UserRestriction.objects.get(user_id=user_id)
            restricted_visibilities = restriction.restricted_to_visibility.all()
            
            return Response({
                'user_id': user_id,
                'restricted_to_visibility': [
                    {'id': v.id, 'name': v.name, 'code': v.code} 
                    for v in restricted_visibilities
                ],
                'max_visibility': restriction.max_visibility,
                'can_create_events': restriction.can_create_events
            })
        except UserRestriction.DoesNotExist:
            return Response({'message': 'No restrictions'})