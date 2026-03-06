import logging
from collections import deque
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import date
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Q, F, Count, Prefetch
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from .models import Person, PersonRelation,Invitation
from apps.relations.models import FixedRelation
from apps.relations.services import RelationLabelService, ConflictDetectionService

# Configure logger
logger = logging.getLogger(__name__)


class BaseSerializerMixin:
    """Common utilities for all serializers."""
    
    def get_user_from_context(self):
        """Safely get user from context."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return request.user
        return None
    
    def get_preferred_language(self):
        """Get user's preferred language from context."""
        user = self.get_user_from_context()
        if user and user.is_authenticated and hasattr(user, 'profile'):
            return getattr(user.profile, 'preferred_language', 'en')
        return 'en'
    
    def handle_validation_error(self, field: str, message: str, code: str = 'invalid') -> None:
        """Consistent error handling."""
        raise ValidationError({field: [{"message": message, "code": code}]})


class PersonSerializer(serializers.ModelSerializer, BaseSerializerMixin):
    """Serializer for Person model with production-level error handling."""
    
    age = serializers.SerializerMethodField()
    
    public_profile = serializers.SerializerMethodField()
    is_current_user = serializers.SerializerMethodField()
    generation = serializers.SerializerMethodField()
    generation_label = serializers.SerializerMethodField()
    immediate_family_count = serializers.SerializerMethodField()
    total_connected_count = serializers.SerializerMethodField()
    
    # Computed fields with caching
    _generation_cache = {}
    _family_count_cache = {}
    
    class Meta:
        model = Person
        fields = [
            'id', 'linked_user', 'full_name', 'gender',
            'date_of_birth', 'date_of_death', 'age',
            'family', 'is_alive', 'is_verified',
            'public_profile', 'is_current_user',
            'generation', 'generation_label',
            'immediate_family_count', 'total_connected_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_verified']
        extra_kwargs = {
            'full_name': {
                'required': True,
                'allow_blank': False,
                'error_messages': {
                    'required': 'Full name is required',
                    'blank': 'Full name cannot be empty'
                }
            },
            'gender': {
                'required': True,
                'error_messages': {
                    'required': 'Gender is required',
                    'invalid_choice': 'Invalid gender choice'
                }
            }
        }

    def __init__(self, *args, **kwargs):
        """Initialize with cache clearing if needed."""
        super().__init__(*args, **kwargs)
        # Clear instance caches if this is a new instance
        if hasattr(self, 'instance') and self.instance:
            self._generation_cache = {}
            self._family_count_cache = {}

    def get_generation(self, obj) -> Optional[int]:
        """
        Calculate generation number relative to current user with caching.
        Returns: 0 for self, positive for ancestors, negative for descendants.
        """
        # Check cache first
        cache_key = f"generation_{obj.id}_{self.get_user_from_context().id if self.get_user_from_context() else 'anon'}"
        if cache_key in self._generation_cache:
            return self._generation_cache[cache_key]
        
        try:
            request = self.context.get('request')
            if not request or not request.user.is_authenticated:
                return None
            
            current_user_person = Person.objects.filter(
                linked_user=request.user
            ).select_related('family').first()
            
            if not current_user_person:
                logger.warning(f"No person record found for user {request.user.id}")
                return None
            
            if obj.id == current_user_person.id:
                self._generation_cache[cache_key] = 0
                return 0
            
            # BFS to find shortest path
            generation = self._calculate_generation_bfs(obj, current_user_person)
            self._generation_cache[cache_key] = generation
            return generation
            
        except Exception as e:
            logger.error(f"Error calculating generation for person {obj.id}: {str(e)}", exc_info=True)
            return None

    def _calculate_generation_bfs(self, target: Person, current: Person, max_depth: int = 10) -> Optional[int]:
        """
        BFS implementation with proper error handling and cycle detection.
        """
        try:
            from collections import deque
            
            # Queue: (person_id, depth, generation_change)
            queue = deque([(current.id, 0, 0)])
            visited = {current.id: (0, 0)}  # person_id -> (depth, generation)
            
            while queue:
                person_id, depth, current_gen = queue.popleft()
                
                if depth > max_depth:
                    continue
                
                # Get all relations with optimized query
                relations = PersonRelation.objects.filter(
                    Q(from_person_id=person_id) | Q(to_person_id=person_id),
                    status__in=['confirmed', 'pending']
                ).select_related('relation').only(
                    'from_person_id', 'to_person_id', 'relation__relation_code'
                )
                
                for rel in relations:
                    try:
                        # Determine other person and calculate generation change
                        if rel.from_person_id == person_id:
                            other_id = rel.to_person_id
                            relation_code = rel.relation.relation_code
                            
                            # Parse direction
                            if relation_code in ['SON', 'DAUGHTER']:
                                new_gen = current_gen + 1  # Other is parent
                            elif relation_code in ['FATHER', 'MOTHER']:
                                new_gen = current_gen - 1  # Other is child
                            else:
                                new_gen = current_gen  # Same generation
                        else:
                            other_id = rel.from_person_id
                            relation_code = rel.relation.relation_code
                            
                            if relation_code in ['SON', 'DAUGHTER']:
                                new_gen = current_gen - 1  # Other is child
                            elif relation_code in ['FATHER', 'MOTHER']:
                                new_gen = current_gen + 1  # Other is parent
                            else:
                                new_gen = current_gen
                        
                        # Skip if already visited with better path
                        if other_id in visited:
                            existing_depth, existing_gen = visited[other_id]
                            if existing_depth <= depth + 1 and abs(existing_gen) <= abs(new_gen):
                                continue
                        
                        visited[other_id] = (depth + 1, new_gen)
                        
                        if other_id == target.id:
                            return new_gen
                        
                        queue.append((other_id, depth + 1, new_gen))
                        
                    except Exception as e:
                        logger.error(f"Error processing relation {rel.id}: {str(e)}")
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"BFS calculation failed: {str(e)}", exc_info=True)
            return None

    def get_generation_label(self, obj) -> str:
        """Get human-readable generation label with proper mapping."""
        try:
            generation = self.get_generation(obj)
            
            if generation is None:
                return "Not in direct lineage"
            
            # Generation labels mapping
            labels = {
                0: "Current Generation",
                1: "First Generation",
                2: "Second Generation",
                3: "Third Generation",
                -1: "Next Generation",
                -2: "Second Next Generation",
                -3: "Third Next Generation"
            }
            
            if generation in labels:
                return labels[generation]
            elif generation > 0:
                return f"{generation}th Generation"
            elif generation < 0:
                return f"{abs(generation)}th Next Generation"
            else:
                return f"Generation {generation}"
                
        except Exception as e:
            logger.error(f"Error getting generation label for person {obj.id}: {str(e)}")
            return "Unknown"

    def get_immediate_family_count(self, obj) -> int:
        """Count immediate family members with caching."""
        cache_key = f"immediate_family_{obj.id}"
        
        # Check cache
        if cache_key in self._family_count_cache:
            return self._family_count_cache[cache_key]
        
        try:
            # Count spouses
            spouse_count = PersonRelation.objects.filter(
                Q(from_person=obj) | Q(to_person=obj),
                relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
                status__in=['confirmed', 'pending']
            ).count()
            
            # Count children
            children_count = PersonRelation.objects.filter(
                from_person=obj,
                relation__relation_code__in=['SON', 'DAUGHTER'],
                status__in=['confirmed', 'pending']
            ).count()
            
            total = spouse_count + children_count
            self._family_count_cache[cache_key] = total
            return total
            
        except Exception as e:
            logger.error(f"Error counting immediate family for person {obj.id}: {str(e)}")
            return 0

    def get_total_connected_count(self, obj) -> int:
        """Count all connected people with caching."""
        cache_key = f"total_connected_{obj.id}"
        
        # Check cache
        if cache_key in self._family_count_cache:
            return self._family_count_cache[cache_key]
        
        try:
            # Get all connected person IDs through relationships
            from_ids = PersonRelation.objects.filter(
                to_person=obj,
                status__in=['confirmed', 'pending']
            ).values_list('from_person_id', flat=True)
            
            to_ids = PersonRelation.objects.filter(
                from_person=obj,
                status__in=['confirmed', 'pending']
            ).values_list('to_person_id', flat=True)
            
            # Get spouse connections
            spouse_relations = PersonRelation.objects.filter(
                Q(from_person=obj) | Q(to_person=obj),
                relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
                status__in=['confirmed', 'pending']
            ).values_list('from_person_id', 'to_person_id')
            
            spouse_connections = []
            for from_id, to_id in spouse_relations:
                if from_id != obj.id:
                    spouse_connections.append(from_id)
                if to_id != obj.id:
                    spouse_connections.append(to_id)
            
            # Combine all unique IDs
            all_connected_ids = set(
                list(from_ids) + list(to_ids) + spouse_connections + [obj.id]
            )
            
            total = len(all_connected_ids)
            self._family_count_cache[cache_key] = total
            return total
            
        except Exception as e:
            logger.error(f"Error counting total connections for person {obj.id}: {str(e)}")
            return 1  # At least self

    def get_age(self, obj) -> Optional[int]:
        """Get age with error handling."""
        try:
            return obj.get_age()
        except Exception as e:
            logger.error(f"Error calculating age for person {obj.id}: {str(e)}")
            return None

    def get_public_profile(self, obj) -> Dict[str, Any]:
        """Get public profile with error handling."""
        try:
            return obj.get_public_profile()
        except Exception as e:
            logger.error(f"Error getting public profile for person {obj.id}: {str(e)}")
            return {"is_public": False}

    def get_is_current_user(self, obj) -> bool:
        """Check if person is current user with error handling."""
        try:
            request = self.context.get('request')
            if request and request.user.is_authenticated:
                return obj.linked_user == request.user
            return False
        except Exception as e:
            logger.error(f"Error checking if person {obj.id} is current user: {str(e)}")
            return False

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate person data with comprehensive checks."""
        try:
            # Validate dates
            if data.get('date_of_birth') and data.get('date_of_death'):
                if data['date_of_death'] < data['date_of_birth']:
                    raise ValidationError({
                        'date_of_death': 'Date of death cannot be before date of birth'
                    })
                
                # Check if date_of_death is in future
                if data['date_of_death'] > timezone.now().date():
                    raise ValidationError({
                        'date_of_death': 'Date of death cannot be in the future'
                    })
            
            # Validate date_of_birth is not in future
            if data.get('date_of_birth') and data['date_of_birth'] > timezone.now().date():
                raise ValidationError({
                    'date_of_birth': 'Date of birth cannot be in the future'
                })
            
            # Validate name length
            if data.get('full_name'):
                if len(data['full_name']) < 2:
                    raise ValidationError({
                        'full_name': 'Name must be at least 2 characters long'
                    })
                if len(data['full_name']) > 200:
                    raise ValidationError({
                        'full_name': 'Name cannot exceed 200 characters'
                    })
            
            # Validate gender
            if data.get('gender') and data['gender'] not in dict(Person.GENDER_CHOICES):
                raise ValidationError({
                    'gender': f"Invalid gender. Must be one of: {', '.join(dict(Person.GENDER_CHOICES).keys())}"
                })
            
            return data
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in person validation: {str(e)}", exc_info=True)
            raise ValidationError("An unexpected error occurred during validation")

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> Person:
        """Create person with transaction support and error handling."""
        request = self.context.get('request')
        
        try:
            # Handle family assignment
            if 'family' not in validated_data:
                validated_data = self._assign_family(validated_data, request)
            
            # Ensure linked_user is None for new persons (except when explicitly set)
            if 'linked_user' not in validated_data:
                validated_data['linked_user'] = None
            
            # Create person
            person = super().create(validated_data)
            
            logger.info(f"Person created successfully: ID {person.id}, Name: {person.full_name}")
            return person
            
        except IntegrityError as e:
            logger.error(f"Database integrity error creating person: {str(e)}", exc_info=True)
            raise ValidationError("A person with this information already exists")
        except Exception as e:
            logger.error(f"Unexpected error creating person: {str(e)}", exc_info=True)
            raise ValidationError("Failed to create person record")

    def _assign_family(self, validated_data: Dict[str, Any], request) -> Dict[str, Any]:
        """Assign family to person with proper error handling."""
        try:
            from apps.families.models import Family
            
            # Get user's person
            user_person = Person.objects.filter(
                linked_user=request.user
            ).select_related('family').first()
            
            if user_person:
                validated_data['family'] = user_person.family
                logger.debug(f"Assigned family {user_person.family.id} from user's person")
            else:
                # Create default family
                family_name = f"{request.user.mobile_number}'s Family" if request.user.mobile_number else "My Family"
                family = Family.objects.create(
                    family_name=family_name,
                    created_by=request.user
                )
                validated_data['family'] = family
                logger.info(f"Created new family {family.id} for user {request.user.id}")
                
                # Create user's person record
                self._create_user_person(request, family)
            
            return validated_data
            
        except Exception as e:
            logger.error(f"Error assigning family: {str(e)}", exc_info=True)
            raise ValidationError("Failed to assign family to person")

    def _create_user_person(self, request, family: 'Family') -> None:
        """Create person record for user with proper error handling."""
        try:
            # Get user's name from profile
            full_name = request.user.mobile_number or "User"
            if hasattr(request.user, 'profile'):
                if request.user.profile.firstname:
                    full_name = request.user.profile.firstname
                elif request.user.profile.lastname:
                    full_name = request.user.profile.lastname
            
            # Get gender from profile
            gender = 'M'  # default
            if hasattr(request.user, 'profile') and request.user.profile.gender:
                gender = request.user.profile.gender
            
            Person.objects.create(
                linked_user=request.user,
                full_name=full_name,
                gender=gender,
                family=family
            )
            logger.info(f"Created user person record for {request.user.id}")
            
        except Exception as e:
            logger.error(f"Error creating user person: {str(e)}", exc_info=True)
            # Don't raise - this is not critical for the main operation

class PersonRelationSerializer(serializers.ModelSerializer, BaseSerializerMixin):
    """Serializer for PersonRelation model with comprehensive error handling."""
    
    from_person_name = serializers.CharField(source='from_person.full_name', read_only=True)
    to_person_name = serializers.CharField(source='to_person.full_name', read_only=True)
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    relation_label = serializers.SerializerMethodField()
    
    # Profile picture fields
    from_person_profile_picture = serializers.SerializerMethodField()
    to_person_profile_picture = serializers.SerializerMethodField()
    
    # Brick properties
    brick_person_id = serializers.SerializerMethodField()
    brick_person_name = serializers.SerializerMethodField()
    brick_person_gender = serializers.SerializerMethodField()
    brick_label = serializers.SerializerMethodField()
    arrow_label = serializers.SerializerMethodField()
    
    conflicts = serializers.SerializerMethodField()
    
    # Gender mapping cache
    _gender_cache = {}
    
    class Meta:
        model = PersonRelation
        fields = [
            'id', 'from_person', 'from_person_name', 'from_person_profile_picture',
            'to_person', 'to_person_name', 'to_person_profile_picture',
            'relation', 'relation_code', 'relation_label',
            'brick_person_id', 'brick_person_name', 'brick_person_gender',
            'brick_label', 'arrow_label',
            'status', 'conflict_reason',
            'conflicts', 'created_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'conflict_reason']
        extra_kwargs = {
            'from_person': {
                'required': True,
                'error_messages': {
                    'required': 'Source person is required',
                    'does_not_exist': 'Source person does not exist'
                }
            },
            'to_person': {
                'required': True,
                'error_messages': {
                    'required': 'Target person is required',
                    'does_not_exist': 'Target person does not exist'
                }
            },
            'relation': {
                'required': True,
                'error_messages': {
                    'required': 'Relation type is required',
                    'does_not_exist': 'Invalid relation type'
                }
            }
        }

    def _get_gender_from_person(self, person: Person) -> str:
        """Consistent gender fetching with caching."""
        cache_key = f"gender_{person.id}"
        
        if cache_key in self._gender_cache:
            return self._gender_cache[cache_key]
        
        try:
            # Check profile first
            if person.linked_user and hasattr(person.linked_user, 'profile'):
                profile_gender = getattr(person.linked_user.profile, 'gender', None)
                if profile_gender in ['M', 'F', 'O']:
                    self._gender_cache[cache_key] = profile_gender
                    return profile_gender
            
            # Fallback to person gender
            gender = person.gender if person.gender in ['M', 'F', 'O'] else 'O'
            self._gender_cache[cache_key] = gender
            return gender
            
        except Exception as e:
            logger.error(f"Error getting gender for person {person.id}: {str(e)}")
            return 'O'

    def _get_base_labels(self, relation_code: str, language: str = 'en') -> Dict[str, str]:
        """Get base relation labels with fallback."""
        BASE_LABELS = {
            'FATHER': {'ta': 'அப்பா', 'en': 'Father'},
            'MOTHER': {'ta': 'அம்மா', 'en': 'Mother'},
            'SON': {'ta': 'மகன்', 'en': 'Son'},
            'DAUGHTER': {'ta': 'மகள்', 'en': 'Daughter'},
            'HUSBAND': {'ta': 'கணவன்', 'en': 'Husband'},
            'WIFE': {'ta': 'மனைவி', 'en': 'Wife'},
            'ELDER_BROTHER': {'ta': 'அண்ணன்', 'en': 'Elder Brother'},
            'YOUNGER_BROTHER': {'ta': 'தம்பி', 'en': 'Younger Brother'},
            'BROTHER': {'ta': 'சகோதரன்', 'en': 'Brother'},
            'ELDER_SISTER': {'ta': 'அக்கா', 'en': 'Elder Sister'},
            'YOUNGER_SISTER': {'ta': 'தங்கை', 'en': 'Younger Sister'},
            'SISTER': {'ta': 'சகோதரி', 'en': 'Sister'},
            'SPOUSE': {'ta': 'துணைவர்', 'en': 'Spouse'},
            'PARTNER': {'ta': 'துணைவர்', 'en': 'Partner'},
        }
        
        label_data = BASE_LABELS.get(relation_code, {
            'ta': relation_code,
            'en': relation_code
        })
        
        return {
            'label': label_data.get(language, label_data['en']),
            'all': label_data
        }

    def _get_inverse_label(self, relation_code: str, my_gender: str, 
                          other_gender: str, language: str = 'en') -> str:
        """Get inverse relation label with comprehensive mapping."""
        INVERSE_MAP = {
            'FATHER': {
                'M': {'ta': 'மகன்', 'en': 'Son'},
                'F': {'ta': 'மகள்', 'en': 'Daughter'},
            },
            'MOTHER': {
                'M': {'ta': 'மகன்', 'en': 'Son'},
                'F': {'ta': 'மகள்', 'en': 'Daughter'},
            },
            'SON': {
                'M': {'ta': 'அப்பா', 'en': 'Father'},
                'F': {'ta': 'அம்மா', 'en': 'Mother'},
            },
            'DAUGHTER': {
                'M': {'ta': 'அப்பா', 'en': 'Father'},
                'F': {'ta': 'அம்மா', 'en': 'Mother'},
            },
            'HUSBAND': {
                'F': {'ta': 'மனைவி', 'en': 'Wife'},
            },
            'WIFE': {
                'M': {'ta': 'கணவன்', 'en': 'Husband'},
            },
            'ELDER_BROTHER': {
                'M': {'ta': 'இளைய சகோதரன்', 'en': 'Younger Brother'},
                'F': {'ta': 'இளைய சகோதரி', 'en': 'Younger Sister'},
            },
            'YOUNGER_BROTHER': {
                'M': {'ta': 'மூத்த சகோதரன்', 'en': 'Elder Brother'},
                'F': {'ta': 'மூத்த சகோதரி', 'en': 'Elder Sister'},
            },
            'BROTHER': {
                'M': {'ta': 'சகோதரன்', 'en': 'Brother'},
                'F': {'ta': 'சகோதரி', 'en': 'Sister'},
            },
            'ELDER_SISTER': {
                'M': {'ta': 'இளைய சகோதரன்', 'en': 'Younger Brother'},
                'F': {'ta': 'இளைய சகோதரி', 'en': 'Younger Sister'},
            },
            'YOUNGER_SISTER': {
                'M': {'ta': 'மூத்த சகோதரன்', 'en': 'Elder Brother'},
                'F': {'ta': 'மூத்த சகோதரி', 'en': 'Elder Sister'},
            },
            'SISTER': {
                'M': {'ta': 'சகோதரன்', 'en': 'Brother'},
                'F': {'ta': 'சகோதரி', 'en': 'Sister'},
            },
            'SPOUSE': {
                'M': {'ta': 'மனைவி', 'en': 'Wife'},
                'F': {'ta': 'கணவன்', 'en': 'Husband'},
            },
        }
        
        try:
            if relation_code in INVERSE_MAP:
                gender_map = INVERSE_MAP[relation_code]
                
                # Try exact gender match
                if my_gender in gender_map:
                    return gender_map[my_gender].get(language, gender_map[my_gender]['en'])
                
                # Fallback to first available
                for gender, labels in gender_map.items():
                    return labels.get(language, labels['en'])
            
            # Default to base label
            return self._get_base_labels(relation_code, language)['label']
            
        except Exception as e:
            logger.error(f"Error getting inverse label for {relation_code}: {str(e)}")
            return relation_code

    def get_relation_label(self, obj) -> Dict[str, Any]:
        """Get relation labels with comprehensive error handling."""
        try:
            request = self.context.get('request')
            me = self.context.get('me')
            viewing_person = self.context.get('viewing_person')
            
            language = self.get_preferred_language()
            
            # Get genders
            from_gender = self._get_gender_from_person(obj.from_person)
            to_gender = self._get_gender_from_person(obj.to_person)
            relation_code = obj.relation.relation_code
            
            # Base response
            base_labels = self._get_base_labels(relation_code, language)
            response = {
                'label': base_labels['label'],
                'source': 'direct',
                'user_label': None,
                'arrow_label': None,
                'all_labels': base_labels['all']
            }
            
            # Handle relation involving 'me'
            if me:
                if obj.to_person == me:
                    # Relation TO me
                    my_gender = to_gender
                    other_gender = from_gender
                    
                    inverse_label = self._get_inverse_label(
                        relation_code, my_gender, other_gender, language
                    )
                    
                    response.update({
                        'user_label': inverse_label,
                        'source': 'inverse_to_me',
                        'arrow_label': self._get_arrow_label_from_perspective(
                            relation_code, my_gender, other_gender, False, language
                        )
                    })
                    return response
                    
                elif obj.from_person == me:
                    # Relation FROM me
                    my_gender = from_gender
                    other_gender = to_gender
                    
                    response.update({
                        'user_label': base_labels['label'],
                        'source': 'direct_from_me',
                        'arrow_label': self._get_arrow_label_from_perspective(
                            relation_code, my_gender, other_gender, True, language
                        )
                    })
                    return response
            
            # Handle viewing someone else's page
            if viewing_person and viewing_person != me:
                derived_label = self._get_derived_label(obj, viewing_person, me, language)
                if derived_label:
                    response.update(derived_label)
                    return response
            
            # Default case
            response.update({
                'user_label': base_labels['label'],
                'arrow_label': self._get_arrow_label_from_perspective(
                    relation_code, from_gender, to_gender, True, language
                )
            })
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting relation label for {obj.id}: {str(e)}", exc_info=True)
            return {
                'label': 'Unknown',
                'source': 'error',
                'user_label': 'Unknown',
                'arrow_label': 'Unknown'
            }

    def _get_derived_label(self, obj, viewing_person, me, language: str) -> Optional[Dict]:
        """Get derived relation label for father's/mother's side."""
        try:
            # Get father and mother relations
            father_rel = PersonRelation.objects.filter(
                to_person=me,
                relation__relation_code='FATHER',
                status__in=['confirmed', 'pending']
            ).select_related('from_person').first()
            
            mother_rel = PersonRelation.objects.filter(
                to_person=me,
                relation__relation_code='MOTHER',
                status__in=['confirmed', 'pending']
            ).select_related('from_person').first()
            
            if not father_rel or not mother_rel:
                return None
            
            my_father = father_rel.from_person
            my_mother = mother_rel.from_person
            relative = obj.from_person
            
            # Check which side
            is_father_side = PersonRelation.objects.filter(
                from_person=relative,
                to_person=my_father,
                status__in=['confirmed', 'pending']
            ).exists()
            
            is_mother_side = PersonRelation.objects.filter(
                from_person=relative,
                to_person=my_mother,
                status__in=['confirmed', 'pending']
            ).exists()
            
            code = obj.relation.relation_code
            
            # Derived labels mapping
            derived_map = {
                "FATHER_SIDE": {
                    "ELDER_BROTHER": {"ta": "பெரியப்பா", "en": "Uncle (Father's Elder Brother)"},
                    "YOUNGER_BROTHER": {"ta": "சித்தப்பா", "en": "Uncle (Father's Younger Brother)"},
                    "BROTHER": {"ta": "சித்தப்பா", "en": "Uncle (Father's Brother)"},
                    "ELDER_SISTER": {"ta": "அத்தை", "en": "Aunt (Father's Sister)"},
                    "YOUNGER_SISTER": {"ta": "அத்தை", "en": "Aunt (Father's Sister)"},
                    "SISTER": {"ta": "அத்தை", "en": "Aunt (Father's Sister)"},
                    "FATHER": {"ta": "தாத்தா", "en": "Grandfather (Father's Father)"},
                    "MOTHER": {"ta": "பாட்டி", "en": "Grandmother (Father's Mother)"},
                    "WIFE": {"ta": "அம்மா", "en": "Mother (Father's Brother's Wife)"}
                },
                "MOTHER_SIDE": {
                    "ELDER_BROTHER": {"ta": "மாமா", "en": "Uncle (Mother's Elder Brother)"},
                    "YOUNGER_BROTHER": {"ta": "மாமா", "en": "Uncle (Mother's Younger Brother)"},
                    "BROTHER": {"ta": "மாமா", "en": "Uncle (Mother's Brother)"},
                    "ELDER_SISTER": {"ta": "பெரியம்மா", "en": "Aunt (Mother's Elder Sister)"},
                    "YOUNGER_SISTER": {"ta": "சித்தி", "en": "Aunt (Mother's Younger Sister)"},
                    "SISTER": {"ta": "சித்தி", "en": "Aunt (Mother's Sister)"},
                    "FATHER": {"ta": "தாத்தா", "en": "Grandfather (Mother's Father)"},
                    "MOTHER": {"ta": "பாட்டி", "en": "Grandmother (Mother's Mother)"},
                    "HUSBAND": {"ta": "அப்பா", "en": "Father (Mother's Sister's Husband)"},
                }
            }
            
            if is_father_side and code in derived_map["FATHER_SIDE"]:
                label_data = derived_map["FATHER_SIDE"][code]
                return {
                    'user_label': label_data.get(language, label_data['en']),
                    'source': 'derived_father_side',
                    'arrow_label': label_data.get(language, label_data['en']),
                    'label': label_data.get(language, label_data['en'])
                }
            
            if is_mother_side and code in derived_map["MOTHER_SIDE"]:
                label_data = derived_map["MOTHER_SIDE"][code]
                return {
                    'user_label': label_data.get(language, label_data['en']),
                    'source': 'derived_mother_side',
                    'arrow_label': label_data.get(language, label_data['en']),
                    'label': label_data.get(language, label_data['en'])
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting derived label: {str(e)}")
            return None

    def _get_arrow_label_from_perspective(self, relation_code: str, my_gender: str,
                                          other_gender: str, viewer_is_from: bool,
                                          language: str) -> str:
        """Generate arrow label from viewer's perspective."""
        try:
            if viewer_is_from:
                # Viewer is sender
                my_relation = self._get_base_labels(relation_code, language)['label']
                their_relation = self._get_inverse_label(
                    relation_code, other_gender, my_gender, language
                )
            else:
                # Viewer is receiver
                their_relation = self._get_base_labels(relation_code, language)['label']
                my_relation = self._get_inverse_label(
                    relation_code, my_gender, other_gender, language
                )
            
            return f"{my_relation} → {their_relation}"
            
        except Exception as e:
            logger.error(f"Error generating arrow label: {str(e)}")
            return f"{relation_code} → {relation_code}"

    def get_brick_person_id(self, obj) -> int:
        """Get brick person ID with error handling."""
        try:
            me = self.context.get('me')
            
            if me:
                if obj.to_person == me:
                    return obj.from_person.id
                elif obj.from_person == me:
                    return obj.to_person.id
            
            return obj.from_person.id
            
        except Exception as e:
            logger.error(f"Error getting brick person ID: {str(e)}")
            return obj.from_person.id

    def get_brick_person_name(self, obj) -> str:
        """Get brick person name with error handling."""
        try:
            me = self.context.get('me')
            
            if me:
                if obj.to_person == me:
                    return obj.from_person.full_name
                elif obj.from_person == me:
                    return obj.to_person.full_name
            
            return obj.from_person.full_name
            
        except Exception as e:
            logger.error(f"Error getting brick person name: {str(e)}")
            return "Unknown"

    def get_brick_person_gender(self, obj) -> str:
        """Get brick person gender with error handling."""
        try:
            me = self.context.get('me')
            
            brick_person = None
            if me:
                if obj.to_person == me:
                    brick_person = obj.from_person
                elif obj.from_person == me:
                    brick_person = obj.to_person
            
            if not brick_person:
                brick_person = obj.from_person
            
            return self._get_gender_from_person(brick_person)
            
        except Exception as e:
            logger.error(f"Error getting brick person gender: {str(e)}")
            return 'O'

    def get_from_person_profile_picture(self, obj) -> Optional[str]:
        """Get profile picture URL for from_person."""
        try:
            if obj.from_person.linked_user and hasattr(obj.from_person.linked_user, 'profile'):
                profile = obj.from_person.linked_user.profile
                if hasattr(profile, 'image') and profile.image:
                    try:
                        return profile.image.url
                    except:
                        return None
            return None
        except Exception as e:
            logger.error(f"Error getting from_person profile picture: {str(e)}")
            return None

    def get_to_person_profile_picture(self, obj) -> Optional[str]:
        """Get profile picture URL for to_person."""
        try:
            if obj.to_person.linked_user and hasattr(obj.to_person.linked_user, 'profile'):
                profile = obj.to_person.linked_user.profile
                if hasattr(profile, 'image') and profile.image:
                    try:
                        return profile.image.url
                    except:
                        return None
            return None
        except Exception as e:
            logger.error(f"Error getting to_person profile picture: {str(e)}")
            return None

    def get_brick_label(self, obj) -> str:
        """Get brick label with error handling."""
        try:
            label_data = self.get_relation_label(obj)
            return label_data.get('user_label') or label_data.get('label', '')
        except Exception as e:
            logger.error(f"Error getting brick label: {str(e)}")
            return "Unknown"

    def get_arrow_label(self, obj) -> str:
        """Get arrow label with error handling."""
        try:
            label_data = self.get_relation_label(obj)
            arrow_label = label_data.get('arrow_label')
            
            if arrow_label:
                return arrow_label
            
            # Fallback generation
            language = self.get_preferred_language()
            me = self.context.get('me')
            
            from_gender = self._get_gender_from_person(obj.from_person)
            to_gender = self._get_gender_from_person(obj.to_person)
            relation_code = obj.relation.relation_code
            
            if me:
                if obj.to_person == me:
                    return self._get_arrow_label_from_perspective(
                        relation_code, to_gender, from_gender, False, language
                    )
                elif obj.from_person == me:
                    return self._get_arrow_label_from_perspective(
                        relation_code, from_gender, to_gender, True, language
                    )
            
            return self._get_arrow_label_from_perspective(
                relation_code, from_gender, to_gender, True, language
            )
            
        except Exception as e:
            logger.error(f"Error getting arrow label: {str(e)}")
            return "Unknown → Unknown"

    def get_conflicts(self, obj) -> List[str]:
        """Get conflicts with error handling."""
        try:
            if obj.status == 'conflicted' and obj.conflict_reason:
                return [reason.strip() for reason in obj.conflict_reason.split(';') if reason.strip()]
            
            # Check for potential conflicts
            if obj.status in ['pending', 'confirmed']:
                conflicts = ConflictDetectionService.detect_conflicts(
                    obj.from_person_id,
                    obj.to_person_id,
                    obj.relation.relation_code
                )
                return conflicts if conflicts else []
            
            return []
            
        except Exception as e:
            logger.error(f"Error detecting conflicts for relation {obj.id}: {str(e)}")
            return []

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate relation data with comprehensive checks."""
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        try:
            # Set created_by
            data['created_by'] = request.user
            
            # Get persons (handle both create and update)
            from_person = data.get('from_person') or (self.instance.from_person if self.instance else None)
            to_person = data.get('to_person') or (self.instance.to_person if self.instance else None)
            relation = data.get('relation') or (self.instance.relation if self.instance else None)
            
            # Basic validations
            if not from_person or not to_person:
                raise ValidationError("Both from_person and to_person are required")
            
            # Check permissions
            if from_person.linked_user and from_person.linked_user != request.user:
                raise PermissionDenied("You can only create relations from your own person record")
            
            # Prevent self-relation
            if from_person.id == to_person.id:
                raise ValidationError("Cannot create relation with self")
            
            # Check family
            if from_person.family != to_person.family:
                raise ValidationError("Persons must be in the same family")
            
            # Check if relation already exists
            if not self.instance:  # Only for create
                existing = PersonRelation.objects.filter(
                    from_person=from_person,
                    to_person=to_person,
                    relation=relation
                ).exists()
                
                if existing:
                    raise ValidationError("This relation already exists")
            
            # Validate gender compatibility
            if relation:
                is_valid = self._validate_gender_compatibility(
                    relation.relation_code,
                    from_person.gender,
                    to_person.gender
                )
                
                if not is_valid:
                    error_msg = self._get_gender_error_message(
                        relation.relation_code,
                        from_person.gender,
                        to_person.gender
                    )
                    raise ValidationError({'relation': error_msg})
            
            # Detect conflicts
            if from_person and to_person and relation:
                conflicts = ConflictDetectionService.detect_conflicts(
                    from_person.id,
                    to_person.id,
                    relation.relation_code
                )
                
                if conflicts:
                    data['status'] = 'conflicted'
                    data['conflict_reason'] = '; '.join(conflicts)
            
            return data
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in relation validation: {str(e)}", exc_info=True)
            raise ValidationError("An unexpected error occurred during validation")

    def _validate_gender_compatibility(self, relation_code: str, 
                                       from_gender: str, to_gender: str) -> bool:
        """Validate gender compatibility with comprehensive rules."""
        
        # Generic relations (any gender)
        generic_relations = ['BROTHER', 'SISTER', 'SIBLING', 'PARTNER', 'RELATIVE']
        if relation_code in generic_relations:
            return True
        
        # Specific gender rules
        rules = {
            'SON': lambda f, t: t == 'M',  # Child must be male
            'DAUGHTER': lambda f, t: t == 'F',  # Child must be female
            'FATHER': lambda f, t: f == 'M',  # Parent must be male
            'MOTHER': lambda f, t: f == 'F',  # Parent must be female
            'HUSBAND': lambda f, t: f == 'M' and t == 'F',  # Husband → Wife
            'WIFE': lambda f, t: f == 'F' and t == 'M',  # Wife → Husband
            'SPOUSE': lambda f, t: (f == 'M' and t == 'F') or (f == 'F' and t == 'M'),  # Opposite genders
            'ELDER_BROTHER': lambda f, t: f == 'M',  # Must be male
            'YOUNGER_BROTHER': lambda f, t: f == 'M',  # Must be male
            'ELDER_SISTER': lambda f, t: f == 'F',  # Must be female
            'YOUNGER_SISTER': lambda f, t: f == 'F',  # Must be female
        }
        
        if relation_code in rules:
            return rules[relation_code](from_gender, to_gender)
        
        # Default to True for unknown relations
        logger.warning(f"No gender rule defined for relation: {relation_code}")
        return True

    def _get_gender_error_message(self, relation_code: str, 
                                  from_gender: str, to_gender: str) -> str:
        """Get user-friendly gender error message."""
        error_messages = {
            'SON': f"Son must be male. Current gender: {self._get_gender_display(to_gender)}",
            'DAUGHTER': f"Daughter must be female. Current gender: {self._get_gender_display(to_gender)}",
            'FATHER': f"Father must be male. Current gender: {self._get_gender_display(from_gender)}",
            'MOTHER': f"Mother must be female. Current gender: {self._get_gender_display(from_gender)}",
            'HUSBAND': f"Husband must be male and wife must be female. Current: {self._get_gender_display(from_gender)} → {self._get_gender_display(to_gender)}",
            'WIFE': f"Wife must be female and husband must be male. Current: {self._get_gender_display(from_gender)} → {self._get_gender_display(to_gender)}",
            'SPOUSE': f"Spouses must be of opposite genders. Current: {self._get_gender_display(from_gender)} → {self._get_gender_display(to_gender)}",
            'ELDER_BROTHER': f"Elder brother must be male. Current gender: {self._get_gender_display(from_gender)}",
            'YOUNGER_BROTHER': f"Younger brother must be male. Current gender: {self._get_gender_display(from_gender)}",
            'ELDER_SISTER': f"Elder sister must be female. Current gender: {self._get_gender_display(from_gender)}",
            'YOUNGER_SISTER': f"Younger sister must be female. Current gender: {self._get_gender_display(from_gender)}",
        }
        
        return error_messages.get(
            relation_code,
            f"Gender incompatible for relation {relation_code}. From: {from_gender}, To: {to_gender}"
        )

    def _get_gender_display(self, gender_code: str) -> str:
        """Convert gender code to display text."""
        gender_map = {'M': 'Male', 'F': 'Female', 'O': 'Other'}
        return gender_map.get(gender_code, gender_code)

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> PersonRelation:
        """Create relation with transaction support."""
        try:
            relation = super().create(validated_data)
            logger.info(f"Relation created: {relation.id} ({relation.from_person_id} → {relation.to_person_id})")
            return relation
            
        except IntegrityError as e:
            logger.error(f"Database integrity error creating relation: {str(e)}", exc_info=True)
            raise ValidationError("Failed to create relation due to database constraint")
        except Exception as e:
            logger.error(f"Unexpected error creating relation: {str(e)}", exc_info=True)
            raise ValidationError("Failed to create relation")

    @transaction.atomic
    def update(self, instance: PersonRelation, validated_data: Dict[str, Any]) -> PersonRelation:
        """Update relation with transaction support."""
        try:
            # Don't allow changing persons after creation
            validated_data.pop('from_person', None)
            validated_data.pop('to_person', None)
            validated_data.pop('relation', None)
            
            relation = super().update(instance, validated_data)
            logger.info(f"Relation updated: {relation.id}")
            return relation
            
        except Exception as e:
            logger.error(f"Error updating relation {instance.id}: {str(e)}", exc_info=True)
            raise ValidationError("Failed to update relation")


class CreatePersonRelationSerializer(serializers.Serializer, BaseSerializerMixin):
    """Serializer for creating person relations with comprehensive validation."""
    
    from_person_id = serializers.IntegerField(required=True)
    to_person_id = serializers.IntegerField(required=True)
    relation_code = serializers.CharField(required=True, max_length=50)
    
    class Meta:
        fields = ['from_person_id', 'to_person_id', 'relation_code']

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and enrich relation data."""
        request = self.context.get('request')
        
        if not request or not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        try:
            # Get persons with select_related for efficiency
            from_person = Person.objects.select_related('family', 'linked_user').get(
                id=data['from_person_id']
            )
            to_person = Person.objects.select_related('family', 'linked_user').get(
                id=data['to_person_id']
            )
        except Person.DoesNotExist as e:
            raise ValidationError(f"Person not found: {str(e)}")
        
        # Get relation
        try:
            relation = FixedRelation.objects.get(relation_code=data['relation_code'])
        except FixedRelation.DoesNotExist:
            valid_codes = FixedRelation.objects.values_list('relation_code', flat=True)[:10]
            raise ValidationError({
                'relation_code': f"Invalid relation code: {data['relation_code']}. Valid examples: {', '.join(valid_codes)}"
            })
        
        # Check permissions
        if from_person.linked_user and from_person.linked_user != request.user:
            raise PermissionDenied("You can only create relations from your own person record")
        
        # Check family
        if from_person.family != to_person.family:
            raise ValidationError("Persons must be in the same family")
        
        # Check for existing relation
        existing = PersonRelation.objects.filter(
            from_person=from_person,
            to_person=to_person,
            relation=relation
        ).exists()
        
        if existing:
            raise ValidationError("This relation already exists")
        
        # Validate gender compatibility
        is_valid = RelationLabelService.validate_gender_compatibility(
            relation.relation_code,
            from_person.gender,
            to_person.gender
        )
        
        if not is_valid:
            raise ValidationError(
                f"Gender incompatible for relation {relation.relation_code}. "
                f"From: {from_person.get_gender_display()}, To: {to_person.get_gender_display()}"
            )
        
        # Add enriched data
        data['from_person'] = from_person
        data['to_person'] = to_person
        data['relation'] = relation
        
        return data

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> PersonRelation:
        """Create relation with transaction support."""
        request = self.context.get('request')
        
        try:
            # Create relation
            person_relation = PersonRelation.objects.create(
                from_person=validated_data['from_person'],
                to_person=validated_data['to_person'],
                relation=validated_data['relation'],
                created_by=request.user
            )
            
            logger.info(f"Relation created via CreatePersonRelationSerializer: {person_relation.id}")
            return person_relation
            
        except IntegrityError as e:
            logger.error(f"Database integrity error: {str(e)}", exc_info=True)
            raise ValidationError("Failed to create relation due to database constraint")
        except Exception as e:
            logger.error(f"Unexpected error creating relation: {str(e)}", exc_info=True)
            raise ValidationError("Failed to create relation")


class ConnectedPersonsRequestSerializer(serializers.Serializer):
    """Serializer for requesting connected persons with validation."""
    
    person_id = serializers.IntegerField(
        required=True,
        help_text="ID of the person to get connections for"
    )
    max_depth = serializers.IntegerField(
        default=3,
        min_value=1,
        max_value=10,
        help_text="Maximum depth of relations to traverse (1-10)"
    )
    include_relations = serializers.BooleanField(
        default=True,
        help_text="Include relation details in response"
    )
    
    def validate_person_id(self, value: int) -> int:
        """Validate that person exists."""
        if not Person.objects.filter(id=value).exists():
            raise ValidationError(f"Person with id {value} does not exist")
        return value


class TreeViewSerializer(serializers.Serializer):
    """Serializer for family tree view with validation."""
    
    center_person_id = serializers.IntegerField(
        required=True,
        help_text="ID of the person to center the tree on"
    )
    max_depth = serializers.IntegerField(
        default=3,
        min_value=1,
        max_value=5,
        help_text="Maximum depth of tree (1-5)"
    )
    include_placeholders = serializers.BooleanField(
        default=True,
        help_text="Include placeholder nodes for missing relations"
    )
    
    def validate_center_person_id(self, value: int) -> int:
        """Validate that person exists."""
        if not Person.objects.filter(id=value).exists():
            raise ValidationError(f"Person with id {value} does not exist")
        return value


class AddRelativeSerializer(serializers.Serializer, BaseSerializerMixin):
    """Serializer for adding relatives with auto-gender feature."""
    
    full_name = serializers.CharField(
        max_length=200,
        required=True,
        error_messages={
            'required': 'Full name is required',
            'blank': 'Full name cannot be empty',
            'max_length': 'Name cannot exceed 200 characters'
        }
    )
    
    relation_to_me = serializers.ChoiceField(
        choices=[
            ('FATHER', 'Father'),
            ('MOTHER', 'Mother'),
            ('SON', 'Son'),
            ('DAUGHTER', 'Daughter'),
            ('HUSBAND', 'Husband'),
            ('WIFE', 'Wife'),
            ('ELDER_BROTHER', 'Elder Brother'),
            ('YOUNGER_BROTHER', 'Younger Brother'),
            ('BROTHER', 'Brother'),
            ('SISTER', 'Sister'),
            ('ELDER_SISTER', 'Elder Sister'),
            ('YOUNGER_SISTER', 'Younger Sister'),
            ('SPOUSE', 'Spouse'),
            ('PARTNER', 'Partner'),
            ('CHILD', 'Child'),
            ('PARENT', 'Parent'),
        ],
        required=True,
        help_text="Relation to current user. For specific relations, gender is auto-set."
    )
    
    gender = serializers.ChoiceField(
        choices=Person.GENDER_CHOICES,
        required=False,
        allow_null=True,
        help_text="Optional. Will be auto-set for father/mother/son/daughter/etc."
    )
    
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date of birth (YYYY-MM-DD)"
    )
    
    date_of_death = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date of death (YYYY-MM-DD)"
    )
    
    # Gender mapping for auto-set
    RELATION_GENDER_MAP = {
        'FATHER': 'M',
        'MOTHER': 'F',
        'SON': 'M',
        'DAUGHTER': 'F',
        'HUSBAND': 'M',
        'WIFE': 'F',
        'BROTHER': 'M',
        'ELDER_BROTHER': 'M',
        'YOUNGER_BROTHER': 'M',
        'SISTER': 'F',
        'ELDER_SISTER': 'F',
        'YOUNGER_SISTER': 'F',
        'SPOUSE': None,  # Gender depends on user's gender
        'PARTNER': None,  # Any gender
        'CHILD': None,    # Must specify
        'PARENT': None,   # Must specify
    }

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and auto-set gender based on relation."""
        try:
            relation_to_me = attrs.get('relation_to_me')
            user_provided_gender = attrs.get('gender')
            
            if not relation_to_me:
                raise ValidationError({'relation_to_me': 'Relation is required'})
            
            # Auto-set gender based on relation
            relation_key = relation_to_me.upper()
            
            if relation_key in self.RELATION_GENDER_MAP:
                auto_gender = self.RELATION_GENDER_MAP[relation_key]
                
                if auto_gender is None:
                    # Need manual gender selection or derive from user's gender
                    if relation_key in ['SPOUSE', 'PARTNER']:
                        # Derive opposite gender for spouse if possible
                        derived_gender = self._derive_spouse_gender()
                        if derived_gender and not user_provided_gender:
                            attrs['gender'] = derived_gender
                        elif not user_provided_gender:
                            raise ValidationError({
                                'gender': f'Please specify gender for {relation_to_me.lower()}'
                            })
                    elif not user_provided_gender:
                        raise ValidationError({
                            'gender': f'Please specify gender for {relation_to_me.lower()}'
                        })
                else:
                    # Auto-set gender
                    if user_provided_gender and user_provided_gender != auto_gender:
                        logger.warning(f"User provided gender {user_provided_gender} overrides auto {auto_gender} for {relation_key}")
                        attrs['gender'] = user_provided_gender
                    else:
                        attrs['gender'] = auto_gender
            
            # Validate dates
            if attrs.get('date_of_birth') and attrs.get('date_of_death'):
                if attrs['date_of_death'] < attrs['date_of_birth']:
                    raise ValidationError({
                        'date_of_death': 'Date of death cannot be before date of birth'
                    })
                
                if attrs['date_of_death'] > timezone.now().date():
                    raise ValidationError({
                        'date_of_death': 'Date of death cannot be in the future'
                    })
            
            if attrs.get('date_of_birth') and attrs['date_of_birth'] > timezone.now().date():
                raise ValidationError({
                    'date_of_birth': 'Date of birth cannot be in the future'
                })
            
            return attrs
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error in AddRelativeSerializer validation: {str(e)}", exc_info=True)
            raise ValidationError("Validation failed")

    def _derive_spouse_gender(self) -> Optional[str]:
        """Derive spouse gender based on current user's gender."""
        try:
            request = self.context.get('request')
            if not request or not request.user.is_authenticated:
                return None
            
            # Get current user's person
            user_person = Person.objects.filter(
                linked_user=request.user
            ).first()
            
            if not user_person:
                return None
            
            # Spouse should be opposite gender
            if user_person.gender == 'M':
                return 'F'
            elif user_person.gender == 'F':
                return 'M'
            
            return None
            
        except Exception as e:
            logger.error(f"Error deriving spouse gender: {str(e)}")
            return None

    def validate_full_name(self, value: str) -> str:
        """Validate full name."""
        if len(value.strip()) < 2:
            raise ValidationError("Name must be at least 2 characters long")
        return value.strip()

    def validate_date_of_birth(self, value: Optional[date]) -> Optional[date]:
        """Validate date of birth."""
        if value and value > timezone.now().date():
            raise ValidationError("Date of birth cannot be in the future")
        return value

    def validate_date_of_death(self, value: Optional[date]) -> Optional[date]:
        """Validate date of death."""
        if value and value > timezone.now().date():
            raise ValidationError("Date of death cannot be in the future")
        return value

    def create(self, validated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create method - actual creation happens in view.
        This is just for passing validated data to the view.
        """
        return validated_data
    
# Add this to your serializers.py

class ConnectedPersonSuggestionSerializer(serializers.Serializer):
    """Serializer for connected person suggestions in search."""
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    mobile_number = serializers.SerializerMethodField()
    gender = serializers.CharField()
    relation_to_me = serializers.SerializerMethodField()
    relation_label = serializers.SerializerMethodField()
    family_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    is_placeholder = serializers.BooleanField()
    age = serializers.SerializerMethodField()
    
    def get_mobile_number(self, obj):
        """Get mobile number from linked user if available."""
        if obj.linked_user:
            return obj.linked_user.mobile_number
        return None
    
    def get_relation_to_me(self, obj):
        """Get relation code to current user."""
        request = self.context.get('request')
        me = self.context.get('me')
        
        if not me or me.id == obj.id:
            return {'code': 'SELF', 'label': 'Yourself'}
        
        # Find direct relation
        relation = PersonRelation.objects.filter(
            Q(from_person=me, to_person=obj) | 
            Q(from_person=obj, to_person=me),
            status='confirmed'
        ).select_related('relation').first()
        
        if relation:
            if relation.from_person == me:
                return {
                    'code': relation.relation.relation_code,
                    'label': relation.relation.default_english
                }
            else:
                # Return inverse relation
                inverse_map = {
                    'FATHER': 'SON', 'MOTHER': 'DAUGHTER',
                    'SON': 'FATHER', 'DAUGHTER': 'MOTHER',
                    'HUSBAND': 'WIFE', 'WIFE': 'HUSBAND',
                    'BROTHER': 'SIBLING', 'SISTER': 'SIBLING',
                    'ELDER_BROTHER': 'YOUNGER_BROTHER',
                    'YOUNGER_BROTHER': 'ELDER_BROTHER',
                    'ELDER_SISTER': 'YOUNGER_SISTER',
                    'YOUNGER_SISTER': 'ELDER_SISTER',
                }
                inverse_code = inverse_map.get(relation.relation.relation_code, 'RELATED')
                return {
                    'code': inverse_code,
                    'label': self._get_relation_label(inverse_code)
                }
        
        # Check if they're in the same family
        if me.family_id == obj.family_id:
            return {'code': 'FAMILY', 'label': 'Family Member'}
        
        return {'code': 'CONNECTED', 'label': 'Connected'}
    
    def _get_relation_label(self, relation_code: str) -> str:
        """Get human-readable relation label."""
        labels = {
            'SELF': 'Yourself',
            'FATHER': 'Father',
            'MOTHER': 'Mother',
            'SON': 'Son',
            'DAUGHTER': 'Daughter',
            'HUSBAND': 'Husband',
            'WIFE': 'Wife',
            'BROTHER': 'Brother',
            'SISTER': 'Sister',
            'SIBLING': 'Sibling',
            'SPOUSE': 'Spouse',
            'ELDER_BROTHER': 'Elder Brother',
            'YOUNGER_BROTHER': 'Younger Brother',
            'ELDER_SISTER': 'Elder Sister',
            'YOUNGER_SISTER': 'Younger Sister',
            'FAMILY': 'Family Member',
            'CONNECTED': 'Connected',
            'RELATED': 'Related',
        }
        return labels.get(relation_code, relation_code)
    
    def get_relation_label(self, obj):
        """Get human-readable relation label."""
        relation = self.get_relation_to_me(obj)
        return relation.get('label', 'Family Member')
    
    def get_family_name(self, obj):
        """Get family name."""
        return obj.family.family_name if obj.family else None
    
    def get_profile_picture(self, obj):
        """Get profile picture URL if available."""
        if obj.linked_user and hasattr(obj.linked_user, 'profile'):
            profile = obj.linked_user.profile
            if hasattr(profile, 'profile_picture') and profile.profile_picture:
                try:
                    return profile.profile_picture.url
                except:
                    return None
        return None
    
    def get_age(self, obj):
        """Get age if available."""
        return obj.get_age()
    
# Add these serializers to your existing serializers.py

class InvitationListSerializer(serializers.ModelSerializer):
    """Serializer for listing invitations"""
    invited_by_name = serializers.SerializerMethodField()
    invited_by_mobile = serializers.CharField(source='invited_by.mobile_number', read_only=True)
    person_name = serializers.CharField(source='person.full_name', read_only=True)
    person_gender = serializers.CharField(source='person.gender', read_only=True)
    person_is_placeholder = serializers.BooleanField(source='person.is_placeholder', read_only=True)
    original_relation_code = serializers.CharField(
        source='original_relation.relation_code', 
        read_only=True,
        default=None
    )
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Invitation
        fields = [
            'id', 'token', 'status', 'created_at', 'accepted_at',
            'invited_by', 'invited_by_name', 'invited_by_mobile',
            'person', 'person_name', 'person_gender', 'person_is_placeholder',
            'original_relation_code', 'placeholder_gender',
            'time_ago', 'is_expired'
        ]
        read_only_fields = fields
    
    def get_invited_by_name(self, obj):
        """Get display name of inviter"""
        if hasattr(obj.invited_by, 'profile') and obj.invited_by.profile.firstname:
            return obj.invited_by.profile.firstname
        return obj.invited_by.mobile_number or f"User_{obj.invited_by.id}"
    
    def get_time_ago(self, obj):
        """Get human-readable time ago string"""
        from django.utils import timezone
        from datetime import timedelta
        
        delta = timezone.now() - obj.created_at
        
        if delta < timedelta(minutes=1):
            return 'Just now'
        elif delta < timedelta(hours=1):
            minutes = int(delta.total_seconds() / 60)
            return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
        elif delta < timedelta(days=1):
            hours = int(delta.total_seconds() / 3600)
            return f'{hours} hour{"s" if hours > 1 else ""} ago'
        elif delta < timedelta(days=7):
            days = delta.days
            return f'{days} day{"s" if days > 1 else ""} ago'
        else:
            return obj.created_at.strftime('%b %d, %Y')


class InvitationDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for single invitation"""
    invited_by = serializers.SerializerMethodField()
    invited_user = serializers.SerializerMethodField()
    person = PersonSerializer(read_only=True)
    original_relation_code = serializers.CharField(
        source='original_relation.relation_code', 
        read_only=True,
        default=None
    )
    relation_label = serializers.SerializerMethodField()
    
    class Meta:
        model = Invitation
        fields = [
            'id', 'token', 'status', 'created_at', 'accepted_at',
            'invited_by', 'invited_user',
            'person', 'original_relation_code', 'placeholder_gender',
            'relation_label', 'is_expired'
        ]
        read_only_fields = fields
    
    def get_invited_by(self, obj):
        """Get inviter details"""
        return {
            'id': obj.invited_by.id,
            'name': self._get_user_display_name(obj.invited_by),
            'mobile_number': obj.invited_by.mobile_number
        }
    
    def get_invited_user(self, obj):
        """Get invited user details"""
        return {
            'id': obj.invited_user.id,
            'name': self._get_user_display_name(obj.invited_user),
            'mobile_number': obj.invited_user.mobile_number
        }
    
    def _get_user_display_name(self, user):
        """Get user display name"""
        if hasattr(user, 'profile') and user.profile.firstname:
            return user.profile.firstname
        return user.mobile_number or f"User_{user.id}"
    
    def get_relation_label(self, obj):
        """Get human-readable relation label"""
        if obj.original_relation:
            return obj.original_relation.default_english
        return None


class InvitationActionSerializer(serializers.Serializer):
    """Serializer for accept/reject actions"""
    action = serializers.ChoiceField(
        choices=['accept', 'reject'],
        required=False,
        help_text="Action to perform (optional, can be determined from URL)"
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional notes for rejection"
    )


class CheckNewInvitationsSerializer(serializers.Serializer):
    """Serializer for checking new invitations"""
    last_check = serializers.DateTimeField(
        required=True,
        help_text="Timestamp of last check (ISO format)"
    )
    
    def validate_last_check(self, value):
        """Validate last_check is not in future"""
        from django.utils import timezone
        if value > timezone.now():
            raise serializers.ValidationError("last_check cannot be in the future")
        return value


class InvitationStatsSerializer(serializers.Serializer):
    """Serializer for invitation statistics"""
    total_pending = serializers.IntegerField()
    total_accepted = serializers.IntegerField()
    total_expired = serializers.IntegerField()
    total_rejected = serializers.IntegerField()
    latest_invitation = InvitationListSerializer(read_only=True)
    
class SentInvitationListSerializer(serializers.ModelSerializer):
    """Serializer for listing invitations you sent to others"""
    # Sender information (you)
    from_user_id = serializers.IntegerField(source='invited_by.id', read_only=True)
    from_user_name = serializers.SerializerMethodField(method_name='get_from_user_name')
    from_user_mobile = serializers.CharField(source='invited_by.mobile_number', read_only=True)
    
    # Recipient information (who you sent it to)
    to_user_id = serializers.IntegerField(source='invited_user.id', read_only=True, default=None)
    to_user_name = serializers.SerializerMethodField(method_name='get_to_user_name')
    to_user_mobile = serializers.CharField(source='invited_user.mobile_number', read_only=True, default=None)
    
    # Person/Placeholder information
    person_name = serializers.CharField(source='person.full_name', read_only=True)
    person_gender = serializers.CharField(source='person.gender', read_only=True)
    person_is_placeholder = serializers.BooleanField(source='person.is_placeholder', read_only=True)
    
    # Recipient type (helps UI determine how to display)
    recipient_type = serializers.SerializerMethodField()
    recipient_display = serializers.SerializerMethodField()
    
    original_relation_code = serializers.CharField(
        source='original_relation.relation_code', 
        read_only=True,
        default=None
    )
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Invitation
        fields = [
            'id', 'token', 'status', 'created_at', 'accepted_at',
            # Sender fields (you)
            'from_user_id', 'from_user_name', 'from_user_mobile',
            # Recipient fields (who you sent to)
            'to_user_id', 'to_user_name', 'to_user_mobile',
            'recipient_type', 'recipient_display',
            # Person fields
            'person', 'person_name', 'person_gender', 'person_is_placeholder',
            'original_relation_code', 'placeholder_gender',
            'time_ago', 'is_expired'
        ]
        read_only_fields = fields
    
    def get_from_user_name(self, obj):
        """Get display name of sender (you)"""
        if hasattr(obj.invited_by, 'profile') and obj.invited_by.profile.firstname:
            return obj.invited_by.profile.firstname
        return obj.invited_by.mobile_number or f"User_{obj.invited_by.id}"
    
    def get_to_user_name(self, obj):
        """Get display name of recipient"""
        if obj.invited_user:
            if hasattr(obj.invited_user, 'profile') and obj.invited_user.profile.firstname:
                return obj.invited_user.profile.firstname
            return obj.invited_user.mobile_number or f"User_{obj.invited_user.id}"
        return None
    
    def get_recipient_type(self, obj):
        """Determine the type of recipient"""
        if obj.invited_user:
            return 'registered_user'
        elif obj.person and obj.person.is_placeholder:
            return 'placeholder'
        else:
            return 'unknown'
    
    def get_recipient_display(self, obj):
        """Get a display string for the recipient"""
        recipient_type = self.get_recipient_type(obj)
        
        if recipient_type == 'registered_user':
            return self.get_to_user_name(obj)
        elif recipient_type == 'placeholder':
            return f"{obj.person.full_name or 'Unknown'} (Placeholder)"
        else:
            return "Unknown recipient"
    
    def get_time_ago(self, obj):
        """Get human-readable time ago string"""
        from django.utils import timezone
        from datetime import timedelta
        
        delta = timezone.now() - obj.created_at
        
        if delta < timedelta(minutes=1):
            return 'Just now'
        elif delta < timedelta(hours=1):
            minutes = int(delta.total_seconds() / 60)
            return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
        elif delta < timedelta(days=1):
            hours = int(delta.total_seconds() / 3600)
            return f'{hours} hour{"s" if hours > 1 else ""} ago'
        elif delta < timedelta(days=7):
            days = delta.days
            return f'{days} day{"s" if days > 1 else ""} ago'
        else:
            return obj.created_at.strftime('%b %d, %Y')