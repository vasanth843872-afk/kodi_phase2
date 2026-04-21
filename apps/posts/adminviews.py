# posts/views.py (add these at the end)

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Post, PostComment, PostReport, PostVisibilityRule
from .serializers import (
    PostAdminDetailSerializer, PostAdminListSerializer,
    PostCommentAdminSerializer, PostReportAdminSerializer,
    PostVisibilityRuleAdminSerializer, PostVisibilityRuleCreateUpdateSerializer
)
from .services import PostVisibilityService, PostEngagementService
from admin_app.permissions import CanManageChat,CanManagePost
from apps.notifications.services import NotificationService, get_user_display_name


# ---------- Post Admin ----------
class AdminPostListView(generics.ListAPIView):
    """GET /admin/posts/ - list all posts (with optional filters)."""
    permission_classes = [IsAuthenticated,CanManagePost]
    serializer_class = PostAdminListSerializer

    def get_queryset(self):
        queryset = Post.objects.all().select_related('author').prefetch_related('reports')
        # Optional filters
        status = self.request.query_params.get('status')
        if status == 'active':
            queryset = queryset.filter(is_active=True, is_deleted=False)
        elif status == 'deleted':
            queryset = queryset.filter(is_deleted=True)
        elif status == 'reported':
            queryset = queryset.filter(is_reported=True)
        return queryset.order_by('-created_at')


class AdminPostDetailView(APIView):
    """GET /admin/posts/<id>/ - detailed post info
       DELETE /admin/posts/<id>/ - hard delete post
       PATCH /admin/posts/<id>/ - toggle active/deleted status
    """
    permission_classes = [IsAuthenticated,CanManagePost]

    def get(self, request, post_id):
        post = get_object_or_404(Post.objects.select_related('author').prefetch_related('media', 'reports'), id=post_id)
        serializer = PostAdminDetailSerializer(post, context={'request': request})
        return Response(serializer.data)

    def delete(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)
        
        # Send notification to post author before deletion
        NotificationService.create_post_notification(
            post=post,
            notification_type='post_deleted',
            users=[post.author],
            message=f"Admin {get_user_display_name(request.user)} deleted your post",
            actor=request.user
        )
        
        post.delete()  # hard delete
        return Response({'detail': 'Post permanently deleted.'}, status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, post_id):
        post = get_object_or_404(Post, id=post_id)
        action = request.data.get('action')
        if action == 'hide':
            post.is_active = False
            post.save(update_fields=['is_active'])
            # Invalidate visibility cache
            PostVisibilityService.invalidate_post_audience(post)
            
            # Send notification to post author
            NotificationService.create_post_notification(
                post=post,
                notification_type='post_visibility_changed',
                users=[post.author],
                message=f"Admin {get_user_display_name(request.user)} hid your post",
                actor=request.user
            )
            
            return Response({'detail': 'Post hidden.'})
        elif action == 'unhide':
            post.is_active = True
            post.save(update_fields=['is_active'])
            PostVisibilityService.precompute_audience_for_post(post)
            
            # Send notification to post author
            NotificationService.create_post_notification(
                post=post,
                notification_type='post_visibility_changed',
                users=[post.author],
                message=f"Admin {get_user_display_name(request.user)} restored your post",
                actor=request.user
            )
            
            return Response({'detail': 'Post restored.'})
        elif action == 'soft_delete':
            post.is_deleted = True
            post.deleted_at = timezone.now()
            post.save(update_fields=['is_deleted', 'deleted_at'])
            PostVisibilityService.invalidate_post_audience(post)
            
            # Send notification to post author
            NotificationService.create_post_notification(
                post=post,
                notification_type='post_deleted',
                users=[post.author],
                message=f"Admin {get_user_display_name(request.user)} deleted your post",
                actor=request.user
            )
            
            return Response({'detail': 'Post soft-deleted.'})
        else:
            return Response({'error': 'Invalid action. Use hide/unhide/soft_delete.'}, status=400)


# ---------- Comment Admin ----------
class AdminCommentListView(generics.ListAPIView):
    """GET /admin/comments/ - list all comments (with optional post_id filter)."""
    permission_classes = [IsAuthenticated,CanManagePost]
    serializer_class = PostCommentAdminSerializer

    def get_queryset(self):
        queryset = PostComment.objects.select_related('author', 'post')
        post_id = self.request.query_params.get('post_id')
        if post_id:
            queryset = queryset.filter(post_id=post_id)
        return queryset.order_by('-created_at')


class AdminCommentDeleteView(APIView):
    """DELETE /admin/comments/<id>/ - permanently delete a comment."""
    permission_classes = [IsAuthenticated,CanManagePost]

    def delete(self, request, comment_id):
        comment = get_object_or_404(PostComment, id=comment_id)
        
        # Send notification to comment author before deletion
        NotificationService.create_post_notification(
            post=comment.post,
            notification_type='post_commented',  # Using same type for comment actions
            users=[comment.author],
            message=f"Admin {get_user_display_name(request.user)} deleted your comment",
            actor=request.user
        )
        
        comment.delete()
        # Update post comment count
        if comment.post:
            comment.post.update_engagement_counts()
        return Response({'detail': 'Comment permanently deleted.'}, status=status.HTTP_204_NO_CONTENT)


# ---------- Report Admin ----------
class AdminReportListView(generics.ListAPIView):
    """GET /admin/reports/ - list all post reports."""
    permission_classes = [IsAuthenticated,CanManagePost]
    serializer_class = PostReportAdminSerializer

    def get_queryset(self):
        queryset = PostReport.objects.select_related('post', 'reported_by', 'reviewed_by')
        status = self.request.query_params.get('status')
        if status == 'pending':
            queryset = queryset.filter(is_reviewed=False)
        elif status == 'reviewed':
            queryset = queryset.filter(is_reviewed=True)
        return queryset.order_by('-created_at')


class AdminReportReviewView(APIView):
    """POST /admin/reports/<id>/review/ - mark report as reviewed and take action."""
    permission_classes = [IsAuthenticated,CanManagePost]

    def post(self, request, report_id):
        report = get_object_or_404(PostReport, id=report_id)
        if report.is_reviewed:
            return Response({'detail': 'Report already reviewed.'}, status=400)

        take_action = request.data.get('take_action', False)
        admin_notes = request.data.get('admin_notes', '')

        report.is_reviewed = True
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.admin_notes = admin_notes

        if take_action:
            # Option 1: hide the post
            post = report.post
            post.is_active = False
            post.save(update_fields=['is_active'])
            PostVisibilityService.invalidate_post_audience(post)
            report.is_action_taken = True

        report.save()
        return Response({'detail': 'Report reviewed.', 'action_taken': take_action})


# ---------- Visibility Rule Admin ----------
class AdminVisibilityRuleListView(generics.ListCreateAPIView):
    """GET /admin/visibility-rules/ - list all rules
       POST /admin/visibility-rules/ - create a new rule
    """
    permission_classes = [IsAuthenticated,CanManagePost]
    queryset = PostVisibilityRule.objects.all().order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PostVisibilityRuleCreateUpdateSerializer
        return PostVisibilityRuleAdminSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminVisibilityRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET /admin/visibility-rules/<id>/ - retrieve rule
       PUT/PATCH /admin/visibility-rules/<id>/ - update rule
       DELETE /admin/visibility-rules/<id>/ - delete rule
    """
    permission_classes = [IsAuthenticated,CanManagePost]
    queryset = PostVisibilityRule.objects.all()
    lookup_url_kwarg = 'rule_id'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return PostVisibilityRuleCreateUpdateSerializer
        return PostVisibilityRuleAdminSerializer


# ---------- Stats Admin ----------
class AdminPostsStatsView(APIView):
    """GET /admin/posts/stats/ - basic statistics for posts."""
    permission_classes = [IsAuthenticated,CanManagePost]

    def get(self, request):
        stats = {
            'total_posts': Post.objects.count(),
            'active_posts': Post.objects.filter(is_active=True, is_deleted=False).count(),
            'deleted_posts': Post.objects.filter(is_deleted=True).count(),
            'reported_posts': Post.objects.filter(is_reported=True).count(),
            'total_comments': PostComment.objects.count(),
            'active_comments': PostComment.objects.filter(is_deleted=False).count(),
            'total_reports': PostReport.objects.count(),
            'pending_reports': PostReport.objects.filter(is_reviewed=False).count(),
            'total_visibility_rules': PostVisibilityRule.objects.count(),
        }
        return Response(stats)