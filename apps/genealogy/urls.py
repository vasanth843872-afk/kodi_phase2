from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import( PersonViewSet, PersonRelationViewSet, TreeView, PersonDetailView,PersonSearchView,InvitationListView,InvitationDetailView,PendingInvitationsView,
    AcceptInvitationView,
    RejectInvitationView,
    CheckNewInvitationsView,
    InvitationStatsView,
    BulkInvitationActionView,
    SentInvitationsView,
    CancelSentInvitationView,
    InvitationWithPathView
    )
# from .views import (
#     AshramamLabelsView,
#     AssignAshramamView,
#     MyAshramamView
# )

router = DefaultRouter()
router.register(r'persons', PersonViewSet, basename='person')
router.register(r'relations', PersonRelationViewSet, basename='person-relation')

urlpatterns = [
    path('', include(router.urls)),
    path('create-relation/', 
        PersonRelationViewSet.as_view({'post': 'create_relation'}),
         name='create-relation'),
    path('tree/',TreeView.as_view(), name='family-tree'),
    path('invitations/sent/', SentInvitationsView.as_view(), name='sent-invitations'),
    
    
    # Person detail with generation info
    path('person/<int:pk>/', PersonDetailView.as_view(), name='person-detail'),
    
    # Generation endpoints
    path('person/<int:pk>/generation-info/', 
         PersonViewSet.as_view({'get': 'generation_info'}), 
         name='person-generation-info'),
    
    path('person/<int:pk>/generation-summary/', 
         PersonViewSet.as_view({'get': 'generation_summary'}), 
         name='generation-summary'),
    
    
    # NEW SEARCH ENDPOINTS
    path('persons/search/', PersonSearchView.as_view(), name='person-search'),
    # Alternative: if using ViewSet action (uncomment if you prefer)
    # path('persons/search/', PersonViewSet.as_view({'get': 'search'}), name='person-search'),
    
    # Full details endpoint after selection
    path('persons/<int:pk>/full-details/', 
        PersonViewSet.as_view({'get': 'full_details'}), 
         name='person-full-details'),
    
    
    path('invitations/sent/<int:pk>/cancel/', 
         CancelSentInvitationView.as_view(), 
         name='cancel-sent-invitation'),
    
    
    
    
    # path("ashramam/labels/", AshramamLabelsView.as_view()),
    # path("ashramam/assign/", AssignAshramamView.as_view()),
    # path("ashramam/my/", MyAshramamView.as_view()),
    
    
    path('invitations/', InvitationListView.as_view(), name='invitation-list'),
    path('invitations/pending/', PendingInvitationsView.as_view(), name='pending-invitations'),
    path('invitations/<int:pk>/', InvitationDetailView.as_view(), name='invitation-detail'),
    path('invitations/<int:pk>/view-with-path/', 
    InvitationWithPathView.as_view(), 
    name='invitation-with-path'),
    path('invitations/<int:pk>/accept/', AcceptInvitationView.as_view(), name='accept-invitation'),
    path('invitations/<int:pk>/reject/', RejectInvitationView.as_view(), name='reject-invitation'),
    path('invitations/check-new/', CheckNewInvitationsView.as_view(), name='check-new-invitations'),
    path('invitations/stats/', InvitationStatsView.as_view(), name='invitation-stats'),
    path('invitations/bulk-action/', BulkInvitationActionView.as_view(), name='bulk-invitation-action'),
    
]

# Available endpoints:
# POST   /api/genealogy/persons/add_relative/     - Add relative with auto-gender
# PUT    /api/genealogy/persons/{id}/update_name/ - Edit name (Option A)
# POST   /api/genealogy/persons/{id}/send_invitation/ - Connect (Option B)
# POST   /api/genealogy/persons/accept-invitation/<token>/  -accept invitation
# GET    /api/genealogy/persons/{id}/next_flow/   - Next flow (Option C)



# ASHRAMAM
# GET /api/ashramam/labels/  --Returns all possible Ashramam address labels
# POST ashramam/assign/ ----Assign a chosen Ashramam relation to a person
# GET ashramam/my/  ----Get all Ashramam connections of the logged-in user