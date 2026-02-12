from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily
from .serializers import (
    FixedRelationSerializer,
    RelationLanguageReligionSerializer,
    RelationCasteSerializer,
    RelationFamilySerializer,
    RelationLabelRequestSerializer,
    BulkRelationLabelsSerializer,
    GenderValidationSerializer
)
from .services import RelationLabelService, ConflictDetectionService

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import FixedRelation
from .serializers import FixedRelationSerializer

class FixedRelationViewSet(viewsets.ReadOnlyModelViewSet):
    """API for getting relations in different languages."""
    queryset = FixedRelation.objects.all()
    serializer_class = FixedRelationSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['get'])
    def by_language(self, request):
        """Get all relations in specific language."""
        language = request.query_params.get('lang', 'en')
        
        # Pass language as query param for serializer
        request.GET._mutable = True
        request.GET['lang'] = language
        
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def dropdown_options(self, request):
        """Get relations formatted for dropdown use."""
        language = request.query_params.get('lang', 'en')
        
        relations = FixedRelation.objects.all()
        options = []
        
        for relation in relations:
            options.append({
                'value': relation.relation_code,
                'label': relation.get_localized_name(language=language),
                'category': relation.category
            })
        
        # Group by category
        grouped = {}
        for option in options:
            category = option['category']
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(option)
        
        return Response(grouped)
class RelationLanguageReligionViewSet(viewsets.ModelViewSet):
    """ViewSet for RelationLanguageReligion (admin only)."""
    queryset = RelationLanguageReligion.objects.all()
    serializer_class = RelationLanguageReligionSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        """Filter by language and/or religion if provided."""
        queryset = super().get_queryset()
        
        language = self.request.query_params.get('language')
        religion = self.request.query_params.get('religion')
        
        if language:
            queryset = queryset.filter(language=language)
        if religion:
            queryset = queryset.filter(religion=religion)
        
        return queryset

class RelationCasteViewSet(viewsets.ModelViewSet):
    """ViewSet for RelationCaste (admin only)."""
    queryset = RelationCaste.objects.all()
    serializer_class = RelationCasteSerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        """Filter by language, religion, and/or caste if provided."""
        queryset = super().get_queryset()
        
        language = self.request.query_params.get('language')
        religion = self.request.query_params.get('religion')
        caste = self.request.query_params.get('caste')
        
        if language:
            queryset = queryset.filter(language=language)
        if religion:
            queryset = queryset.filter(religion=religion)
        if caste:
            queryset = queryset.filter(caste=caste)
        
        return queryset

class RelationFamilyViewSet(viewsets.ModelViewSet):
    """ViewSet for RelationFamily (admin only)."""
    queryset = RelationFamily.objects.all()
    serializer_class = RelationFamilySerializer
    permission_classes = [permissions.IsAdminUser]
    
    def get_queryset(self):
        """Filter by family name if provided."""
        queryset = super().get_queryset()
        
        family = self.request.query_params.get('family')
        if family:
            queryset = queryset.filter(family=family)
        
        return queryset

class RelationLabelViewSet(viewsets.ViewSet):
    """ViewSet for relation label resolution."""
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['post'])
    def get_label(self, request):
        """Get label for a specific relation."""
        serializer = RelationLabelRequestSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            
            # Get user's profile for context
            profile = request.user.profile
            
            label_info = RelationLabelService.get_relation_label(
                relation_code=data['relation_code'],
                language=data.get('language') or profile.preferred_language or 'en',
                religion=data.get('religion') or profile.religion or '',
                caste=data.get('caste') or profile.caste or '',
                family_name=data.get('family_name', '')
            )
            
            return Response(label_info)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def bulk_labels(self, request):
        """Get labels for multiple relations."""
        serializer = BulkRelationLabelsSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            
            # Get user's profile for context
            profile = request.user.profile
            
            # If specific codes provided, use them
            if data.get('relation_codes'):
                results = {}
                for code in data['relation_codes']:
                    label_info = RelationLabelService.get_relation_label(
                        relation_code=code,
                        language=data.get('language') or profile.preferred_language or 'en',
                        religion=data.get('religion') or profile.religion or '',
                        caste=data.get('caste') or profile.caste or '',
                        family_name=data.get('family_name', '')
                    )
                    results[code] = label_info['label']
            else:
                # Get all labels for context
                results = RelationLabelService.get_all_labels_for_context(
                    language=data.get('language') or profile.preferred_language or 'en',
                    religion=data.get('religion') or profile.religion or '',
                    caste=data.get('caste') or profile.caste or '',
                    family_name=data.get('family_name', '')
                )
            
            return Response({'labels': results})
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def validate_gender(self, request):
        """Validate gender compatibility for a relation."""
        serializer = GenderValidationSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            
            is_valid = RelationLabelService.validate_gender_compatibility(
                relation_code=data['relation_code'],
                from_gender=data['from_gender'],
                to_gender=data['to_gender']
            )
            
            return Response({
                'is_valid': is_valid,
                'relation_code': data['relation_code']
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def detect_conflicts(self, request):
        """Detect conflicts for a proposed relation."""
        from_person_id = request.data.get('from_person_id')
        to_person_id = request.data.get('to_person_id')
        relation_code = request.data.get('relation_code')
        
        if not all([from_person_id, to_person_id, relation_code]):
            return Response(
                {'error': 'from_person_id, to_person_id, and relation_code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        conflicts = ConflictDetectionService.detect_conflicts(
            from_person_id, to_person_id, relation_code
        )
        
        return Response({
            'has_conflicts': len(conflicts) > 0,
            'conflicts': conflicts
        })
        

# api/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
import json

from .services import RelationAutomationEngine
from apps.genealogy.models import Person

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_relation_from_path(request):
    """
    Calculate relation from click path.
    
    Request JSON:
    {
        "from_person_id": 1,
        "path": ["father", "brother"],
        "context": {
            "language": "ta",
            "religion": "Hindu",
            "caste": "Brahmin",
            "family_name": "Sharma"
        }
    }
    """
    try:
        data = request.data
        
        # Get person objects
        # from_person = Person.objects.get(
        #     id=data['from_person_id'],
        #     linked_user=request.user  # Security check
        # )
        
        from_person = Person.objects.filter(
            linked_user=request.user
        ).first()
        
        # Calculate relation
        result = RelationAutomationEngine.calculate_relation_from_path(
            from_person=from_person,
            path_elements=data['path'],
            context=data.get('context', {})
        )
        
        return Response({
            'success': True,
            'result': result
        })
        
    except Person.DoesNotExist:
        return Response(
            {'error': 'Person not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def suggest_relations(request):
    """
    Suggest possible relations between two people.
    
    Request JSON:
    {
        "from_person_id": 1,
        "to_person_id": 5,
        "max_depth": 3
    }
    """
    try:
        data = request.data
        
        from_person = Person.objects.get(
            id=data['from_person_id'],
            user=request.user
        )
        to_person = Person.objects.get(
            id=data['to_person_id'],
            user=request.user
        )
        
        suggestions = RelationAutomationEngine.suggest_relation(
            from_person=from_person,
            to_person=to_person,
            max_depth=data.get('max_depth', 3)
        )
        
        return Response({
            'success': True,
            'from_person': from_person.name,
            'to_person': to_person.name,
            'suggestions': suggestions,
            'total_suggestions': len(suggestions)
        })
        
    except Person.DoesNotExist:
        return Response(
            {'error': 'Person not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_relation_examples(request):
    """
    Get example click paths and their resulting relations.
    Useful for UI demonstration.
    """
    examples = [
        {
            'path': ['father', 'father'],
            'expected_tamil': 'பாட்டன்',
            'expected_english': 'Paternal Grandfather',
            'explanation': "Father's father = Grandfather"
        },
        {
            'path': ['mother', 'brother'],
            'expected_tamil': 'மாமா',
            'expected_english': 'Maternal Uncle',
            'explanation': "Mother's brother = Uncle"
        },
        {
            'path': ['father', 'sister'],
            'expected_tamil': 'அத்தை',
            'expected_english': 'Paternal Aunt',
            'explanation': "Father's sister = Aunt"
        },
        {
            'path': ['mother', 'sister', 'husband'],
            'expected_tamil': 'மாமா/சித்தப்பா',
            'expected_english': 'Maternal Aunt\'s Husband',
            'explanation': "Mother's sister's husband = Uncle"
        },
        {
            'path': ['brother', 'wife'],
            'expected_tamil': 'அண்ணி',
            'expected_english': 'Sister-in-law',
            'explanation': "Brother's wife = Sister-in-law"
        },
        {
            'path': ['father', 'brother', 'son'],
            'expected_tamil': 'சகோதரன்',
            'expected_english': 'Cousin',
            'explanation': "Father's brother's son = Cousin"
        }
    ]
    
    return Response({
        'examples': examples,
        'instructions': 'Send path array to /api/calculate-relation/'
    })