from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import RelationAutoSuggestViewSet

router = DefaultRouter()
# router.register(r'relation-suggest',RelationAutoSuggestViewSet, basename='relation-suggest')
router.register(r'staff', views.StaffManagementViewSet, basename='staff')
router.register(r'users', views.UserManagementViewSet, basename='users')
router.register(r'relation-permissions', views.RelationManagementPermissionViewSet, basename='relation-permissions')
router.register(r'relation-activity-logs', views.RelationAdminActivityLogViewSet, basename='relation-activity-logs')
router.register(r'fixed-relations', views.FixedRelationAdminViewSet, basename='fixed-relations')
router.register(r'relation-overrides', views.RelationOverrideViewSet, basename='relation-overrides')
router.register(r'profile-overrides', views.ProfileOverrideViewSet, basename='profile-override')
router.register(r'admin-activity-logs', views.AdminActivityLogViewSet, basename='admin-activity-logs')


router.register(r'auto-suggest/user', views.UserEnteredAutoSuggestViewSet, basename='user-suggest')

urlpatterns = [
    path('auth/login/', views.AdminLoginView.as_view(), name='admin-login'),
    path('auth/register/', views.CreateInitialAdminView.as_view(), name='admin-register'),
    path('profile/', views.AdminProfileView.as_view(), name='admin-profile'),
    path('dashboard/', views.AdminDashboardView.as_view(), name='admin-dashboard'),
    path('', include(router.urls)),
    
    
    path('relation-label-test/', views.RelationLabelTestView.as_view(), name='relation-label-test'),
    path('relation-analytics/', views.RelationAnalyticsView.as_view(), name='relation-analytics'),
    path('relation-suggest/caste/', RelationAutoSuggestViewSet.as_view({'get': 'caste'}), name='suggest-caste'),
    path('relation-suggest/family/', RelationAutoSuggestViewSet.as_view({'get': 'family'}), name='suggest-family'),
    path('relation-suggest/relation/', RelationAutoSuggestViewSet.as_view({'get': 'relation'}), name='suggest-relation'),
    path('relation-suggest/language/', RelationAutoSuggestViewSet.as_view({'get': 'language'}), name='suggest-language'),
    path('relation-suggest/religion/', RelationAutoSuggestViewSet.as_view({'get': 'religion'}), name='suggest-religion'),
    path('relation-suggest/all-fields/', RelationAutoSuggestViewSet.as_view({'get': 'all_fields'}), name='all-fields'),
    
    
    
    
    path('admin/change-password/', views.AdminChangePasswordView.as_view(), name='admin-change-password'),
    
    
    path('staff/me/profile/',views.StaffSelfProfileView.as_view(), name='staff-self-profile'),
    path('staff/me/change-password/',views.StaffSelfChangePasswordView.as_view(), name='staff-self-change-password'),
    
    path('permissions/list/', views.PermissionListView.as_view(), name='permission-list'),
    path('permissions/my/', views.CurrentUserPermissionsView.as_view(), name='my-permissions'),
    # path('staff/<int:staff_id>/permissions/', views.StaffPermissionUpdateView.as_view(), name='staff-permissions'),
    
    path('staff/<int:staff_id>/permissions/', 
         views.StaffPermissionsManageView.as_view(), 
         name='staff-permissions-manage'),
    
    # Permission templates
    path('permissions/templates/', 
         views.PermissionTemplatesView.as_view(), 
         name='permission-templates'),
    ]