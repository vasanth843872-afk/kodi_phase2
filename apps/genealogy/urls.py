from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PersonViewSet, PersonRelationViewSet, TreeView, PersonDetailView
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
    
    
    # Person detail with generation info
    path('person/<int:pk>/', PersonDetailView.as_view(), name='person-detail'),
    
    # Generation endpoints
    path('person/<int:pk>/generation-info/', 
         PersonViewSet.as_view({'get': 'generation_info'}), 
         name='person-generation-info'),
    
    path('person/<int:pk>/generation-summary/', 
         PersonViewSet.as_view({'get': 'generation_summary'}), 
         name='generation-summary'),
    
    
    # path("ashramam/labels/", AshramamLabelsView.as_view()),
    # path("ashramam/assign/", AssignAshramamView.as_view()),
    # path("ashramam/my/", MyAshramamView.as_view()),
    
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