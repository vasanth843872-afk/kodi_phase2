from django.urls import path
from . import views
from .adminviews import (
    # ... your existing public views ...
    AdminPostListView, AdminPostDetailView,
    AdminCommentListView, AdminCommentDeleteView,
    AdminReportListView, AdminReportReviewView,
    AdminVisibilityRuleListView, AdminVisibilityRuleDetailView,
    AdminPostsStatsView,
)

app_name = 'posts'

urlpatterns = [
    # Post CRUD operations
    path('create/', views.PostCreateView.as_view(), name='post-create'),
    path('<int:post_id>/update/', views.PostUpdateView.as_view(), name='post-update'),
    path('<int:post_id>/delete/', views.PostDeleteView.as_view(), name='post-delete'),
    path('<int:post_id>/', views.PostDetailView.as_view(), name='post-detail'),
    
    # Feed and listing
    path('feed/', views.PostFeedView.as_view(), name='post-feed'),
    
    # Post interactions
    path('<int:post_id>/like/', views.PostLikeView.as_view(), name='post-like'),
    path('<int:post_id>/share/', views.PostShareView.as_view(), name='post-share'),
    path('<int:post_id>/save/', views.PostSaveView.as_view(), name='post-save'),
    path('<int:post_id>/report/', views.PostReportView.as_view(), name='post-report'),
    
    # Comments
    path('<int:post_id>/comments/', views.PostCommentListView.as_view(), name='post-comment-list'),
    path('<int:post_id>/comments/create/', views.PostCommentCreateView.as_view(), name='post-comment-create'),
    
    # Media
    path('<int:post_id>/media/upload/', views.PostMediaUploadView.as_view(), name='post-media-upload'),
    
    
    # admin
    
    path('admin/posts/', AdminPostListView.as_view(), name='admin-posts-list'),
    path('admin/posts/<int:post_id>/', AdminPostDetailView.as_view(), name='admin-posts-detail'),
    path('admin/comments/', AdminCommentListView.as_view(), name='admin-comments-list'),
    path('admin/comments/<int:comment_id>/delete/', AdminCommentDeleteView.as_view(), name='admin-comment-delete'),
    path('admin/reports/', AdminReportListView.as_view(), name='admin-reports-list'),
    path('admin/reports/<int:report_id>/review/', AdminReportReviewView.as_view(), name='admin-report-review'),
    path('admin/visibility-rules/', AdminVisibilityRuleListView.as_view(), name='admin-visibility-rules-list'),
    path('admin/visibility-rules/<int:rule_id>/', AdminVisibilityRuleDetailView.as_view(), name='admin-visibility-rules-detail'),
    path('admin/posts/stats/', AdminPostsStatsView.as_view(), name='admin-posts-stats'),
]
