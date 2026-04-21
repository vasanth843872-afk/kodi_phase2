from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'fixed-relations', views.FixedRelationViewSet, basename='fixed-relation')
router.register(r'language-lifestyle', views.RelationLanguageLifestyleViewSet, basename='language-lifestyle')
router.register(r'familyname8', views.Relationfamilyname8ViewSet, basename='familyname8')
router.register(r'family', views.RelationFamilyViewSet, basename='family')
router.register(r'labels', views.RelationLabelViewSet, basename='label')


urlpatterns = [
    path('', include(router.urls)),
    path('calculate-relation/', views.calculate_relation_from_path, name='calculate_relation'),
    path('suggest-relations/', views.suggest_relations, name='suggest_relations'),
    path('relation-examples/', views.get_relation_examples, name='relation_examples'),
]