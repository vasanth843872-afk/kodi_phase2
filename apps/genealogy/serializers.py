from rest_framework import serializers
from django.utils import timezone
from rest_framework import serializers
from django.db.models import Q
from .models import Person, PersonRelation
from apps.relations.models import FixedRelation
from apps.relations.services import RelationLabelService, ConflictDetectionService

class PersonSerializer(serializers.ModelSerializer):
    """Serializer for Person model."""
    
    age = serializers.SerializerMethodField()
    public_profile = serializers.SerializerMethodField()
    is_current_user = serializers.SerializerMethodField()
    
    generation = serializers.SerializerMethodField()
    generation_label = serializers.SerializerMethodField()
    immediate_family_count = serializers.SerializerMethodField()
    total_connected_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Person
        fields = [
            'id', 'linked_user', 'full_name', 'gender',
            'date_of_birth', 'date_of_death', 'age',
            'family', 'is_alive', 'is_verified',
            'public_profile', 'is_current_user',
            'generation', 'generation_label',  # New fields
            'immediate_family_count', 'total_connected_count',  # New fields
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
        
    def get_generation(self, obj):
        """
        Calculate generation number relative to current user.
        Returns: 0 for current user, 1 for parent, 2 for grandparent, etc.
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        
        # Get current user's person
        current_user_person = Person.objects.filter(linked_user=request.user).first()
        if not current_user_person:
            return None
        
        # If viewing current user
        if obj == current_user_person:
            return 0
        
        # Calculate generation by traversing parent relationships
        return self._calculate_generation_distance(obj, current_user_person)
    
    def _calculate_generation_distance(self, target_person, current_person, max_depth=10):
        """
        Calculate generation distance between two persons.
        Positive = target is ancestor (father/grandfather)
        Negative = target is descendant (son/grandson)
        """
        # Check if target is ancestor of current person
        generation = self._find_ancestor_generation(target_person, current_person, max_depth)
        if generation is not None:
            return generation
        
        # Check if target is descendant of current person
        generation = self._find_descendant_generation(target_person, current_person, max_depth)
        if generation is not None:
            return generation * -1  # Negative for descendants
        
        # Not directly related in lineage
        return None
    
    def _find_ancestor_generation(self, ancestor, person, max_depth, current_depth=0):
        """Find how many generations above the person the ancestor is."""
        if current_depth > max_depth:
            return None
        
        if ancestor == person:
            return current_depth
        
        # Get parents of current person
        parents = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['FATHER', 'MOTHER']
        ).select_related('from_person')
        
        for parent_rel in parents:
            parent = parent_rel.from_person
            result = self._find_ancestor_generation(ancestor, parent, max_depth, current_depth + 1)
            if result is not None:
                return result
        
        return None
    
    def _find_descendant_generation(self, descendant, person, max_depth, current_depth=0):
        """Find how many generations below the person the descendant is."""
        if current_depth > max_depth:
            return None
        
        if descendant == person:
            return current_depth
        
        # Get children of current person
        children = PersonRelation.objects.filter(
            from_person=person,
            relation__relation_code__in=['SON', 'DAUGHTER']
        ).select_related('to_person')
        
        for child_rel in children:
            child = child_rel.to_person
            result = self._find_descendant_generation(descendant, child, max_depth, current_depth + 1)
            if result is not None:
                return result
        
        return None
    
    def get_generation_label(self, obj):
        """Get human-readable generation label."""
        generation = self.get_generation(obj)
        
        if generation is None:
            return "Not in direct lineage"
        
        if generation == 0:
            return "Current Generation"
        elif generation == 1:
            return "First Generation"
        elif generation == 2:
            return "Second Generation"
        elif generation == 3:
            return "Third Generation"
        elif generation > 0:
            return f"{generation}th Generation"
        elif generation == -1:
            return "Next Generation"
        elif generation == -2:
            return "Second Next Generation"
        elif generation < 0:
            return f"{abs(generation)}th Next Generation"
        else:
            return f"Generation {generation}"
    
    def get_immediate_family_count(self, obj):
        """
        Count immediate family members:
        - Spouse(s)
        - Children
        Does NOT include the person themselves.
        """
        # Count spouses
        spouse_count = PersonRelation.objects.filter(
            Q(from_person=obj) | Q(to_person=obj),
            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE']
        ).count()
        
        # Count children (both sons and daughters)
        children_count = PersonRelation.objects.filter(
            from_person=obj,
            relation__relation_code__in=['SON', 'DAUGHTER']
        ).count()
        
        return spouse_count + children_count
    
    def get_total_connected_count(self, obj):
        """
        Count all connected people in the family tree.
        This includes:
        - Self
        - Spouse(s)
        - Children
        - Parents
        - Siblings
        - Grandparents
        - Grandchildren
        - etc.
        """
        # Get all unique person IDs connected through relationships
        from_ids = PersonRelation.objects.filter(
            to_person=obj
        ).values_list('from_person_id', flat=True)
        
        to_ids = PersonRelation.objects.filter(
            from_person=obj
        ).values_list('to_person_id', flat=True)
        
        # Also get people connected through spouse's relationships
        spouse_ids = PersonRelation.objects.filter(
            Q(from_person=obj) | Q(to_person=obj),
            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE']
        ).values_list('from_person_id', 'to_person_id')
        
        # Flatten spouse connections
        spouse_connections = []
        for from_id, to_id in spouse_ids:
            if from_id != obj.id:
                spouse_connections.append(from_id)
            if to_id != obj.id:
                spouse_connections.append(to_id)
        
        # Combine all IDs
        all_connected_ids = set(list(from_ids) + list(to_ids) + spouse_connections + [obj.id])
        
        return len(all_connected_ids)
    
    # Rest of your existing methods remain the same...
    def get_age(self, obj):
        return obj.get_age()
    
    def get_public_profile(self, obj):
        return obj.get_public_profile()
    
    def get_is_current_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.linked_user == request.user
        return False
        
    def get_age(self, obj):
        return obj.get_age()
    
    def get_public_profile(self, obj):
        return obj.get_public_profile()
    
    def get_is_current_user(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.linked_user == request.user
        return False
    
    def validate(self, data):
        """Validate person data."""
        relation = data.get("relation_to_me")

        if relation == "ASHRAMAM":
            # Step A: only click
            if "address_code" not in data:
                return data

            # Step B: creating person
            if not data.get("full_name"):
                raise serializers.ValidationError("Name is required")
        
        if data.get('date_of_birth') and data.get('date_of_death'):
            if data['date_of_death'] < data['date_of_birth']:
                raise serializers.ValidationError({
                    'date_of_death': 'Date of death cannot be before date of birth'
                })
        
        return data
    
    def create(self, validated_data):
        request = self.context.get('request')
    
        # If no family specified, use user's family
        if 'family' not in validated_data:
            # Get or create user's family
            from apps.families.models import Family
            from .models import Person
            
            # Get user's person (should exist after auto-creation)
            user_person = Person.objects.filter(linked_user=request.user).first()
        
            if user_person:
                validated_data['family'] = user_person.family
            else:
                # Create default family for user
                family = Family.objects.create(
                    family_name=f"{request.user.mobile_number}'s Family",
                    created_by=request.user
                )
                validated_data['family'] = family
                
                # Also create user's person record with gender from profile
                # Get gender from user profile
                profile_gender = 'M'  # default
                if hasattr(request.user, 'profile') and request.user.profile.gender:
                    profile_gender = request.user.profile.gender
                
                Person.objects.create(
                    linked_user=request.user,
                    full_name=request.user.profile.firstname or request.user.mobile_number,
                    gender=profile_gender,  # Use gender from profile
                    family=family
                )

        # For adding others, linked_user should be null
        if 'linked_user' not in validated_data:
            validated_data['linked_user'] = None
        
        return super().create(validated_data)


class PersonRelationSerializer(serializers.ModelSerializer):
    """Serializer for PersonRelation model."""
    from_person_name = serializers.CharField(source='from_person.full_name', read_only=True)
    to_person_name = serializers.CharField(source='to_person.full_name', read_only=True)
    relation_code = serializers.CharField(source='relation.relation_code', read_only=True)
    relation_label = serializers.SerializerMethodField()
    
    # Brick properties for frontend display
    brick_person_id = serializers.SerializerMethodField()
    brick_person_name = serializers.SerializerMethodField()
    brick_person_gender = serializers.SerializerMethodField()
    brick_label = serializers.SerializerMethodField()
    arrow_label = serializers.SerializerMethodField()
    
    conflicts = serializers.SerializerMethodField()
    
    class Meta:
        model = PersonRelation
        fields = [
            'id', 'from_person', 'from_person_name',
            'to_person', 'to_person_name',
            'relation', 'relation_code', 'relation_label',
            'brick_person_id', 'brick_person_name', 'brick_person_gender',
            'brick_label', 'arrow_label',
            'status', 'conflict_reason',
            'conflicts', 'created_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at', 'conflict_reason']
    
    def _get_gender_from_person(self, person):
        """Consistent gender fetching - profile first, then person record."""
        if person.linked_user and hasattr(person.linked_user, 'profile'):
            profile_gender = getattr(person.linked_user.profile, 'gender', None)
            if profile_gender in ['M', 'F', 'O']:
                return profile_gender
        return person.gender
    
    def _get_base_labels(self, relation_code, language='en'):
        """Get base relation labels based on relation code."""
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
        }
        
        label_data = BASE_LABELS.get(relation_code, {'ta': relation_code, 'en': relation_code})
        return label_data.get(language, label_data['en'])
    
    def _get_inverse_label(self, relation_code, my_gender, other_gender, language='en'):
        """Get the inverse relation label based on genders."""
        # Define inverse mappings
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
        
        if relation_code in INVERSE_MAP:
            gender_map = INVERSE_MAP[relation_code]
            # Try exact gender match first
            if my_gender in gender_map:
                return gender_map[my_gender].get(language, gender_map[my_gender]['en'])
            # Fallback to first available
            for gender, labels in gender_map.items():
                return labels.get(language, labels['en'])
        
        return self._get_base_labels(relation_code, language)
    
    def _get_perspective_arrow_label(self, relation_code, viewer_gender, other_gender, viewer_is_from, language='en'):
        """
        Get arrow label from viewer's perspective.
        
        Args:
            relation_code: The relation code in the database (from_person → to_person)
            viewer_gender: Gender of the person viewing
            other_gender: Gender of the other person in relation
            viewer_is_from: True if viewer is from_person, False if viewer is to_person
            language: Language code
        """
        if viewer_is_from:
            # Viewer is from_person (sender/initiator)
            # Show: "My Relation → Their Relation to Me"
            my_relation = self._get_base_labels(relation_code, language)
            their_relation = self._get_inverse_label(relation_code, other_gender, viewer_gender, language)
        else:
            # Viewer is to_person (receiver)
            # Show: "Their Relation to Me → My Relation"
            their_relation = self._get_base_labels(relation_code, language)
            my_relation = self._get_inverse_label(relation_code, viewer_gender, other_gender, language)
        
        return f"{my_relation} → {their_relation}"
    
    def get_relation_label(self, obj):
        """Get relation labels with both perspectives."""
        request = self.context.get('request')
        me = self.context.get('me')
        viewing_person = self.context.get('viewing_person')
        
        language = 'en'
        if request and request.user.is_authenticated and hasattr(request.user, 'profile'):
            language = request.user.profile.preferred_language or 'en'
        
        # Get genders
        from_gender = self._get_gender_from_person(obj.from_person)
        to_gender = self._get_gender_from_person(obj.to_person)
        relation_code = obj.relation.relation_code
        
        # Default base response
        base = {
            'label': self._get_base_labels(relation_code, language),
            'source': 'direct',
            'user_label': None,
            'arrow_label': None
        }
        
        # If 'me' is provided in context
        if me:
            # Check if relation involves 'me'
            if obj.to_person == me:
                # Relation TO me: someone → me (I'm receiver)
                my_gender = to_gender
                other_gender = from_gender
                
                # What I call the other person (inverse from my perspective)
                inverse_label = self._get_inverse_label(relation_code, my_gender, other_gender, language)
                base['user_label'] = inverse_label
                base['source'] = 'inverse_to_me'
                
                # Create arrow label from MY perspective (as receiver)
                base['arrow_label'] = self._get_perspective_arrow_label(
                    relation_code, my_gender, other_gender, 
                    viewer_is_from=False, language=language
                )
                
                return base
                
            elif obj.from_person == me:
                # Relation FROM me: me → someone (I'm sender)
                my_gender = from_gender
                other_gender = to_gender
                
                # What I call the other person (direct)
                base['user_label'] = self._get_base_labels(relation_code, language)
                base['source'] = 'direct_from_me'
                
                # Create arrow label from MY perspective (as sender)
                base['arrow_label'] = self._get_perspective_arrow_label(
                    relation_code, my_gender, other_gender,
                    viewer_is_from=True, language=language
                )
                
                return base
        
        # If viewing someone else's page
        if viewing_person and viewing_person != me:
            # Handle derived relations (father's side, mother's side)
            father_rel = PersonRelation.objects.filter(
                to_person=me,
                relation__relation_code='FATHER',
            ).first()
            
            mother_rel = PersonRelation.objects.filter(
                to_person=me,
                relation__relation_code='MOTHER'
            ).first()

            if father_rel and mother_rel:
                my_father = father_rel.from_person
                my_mother = mother_rel.from_person
                
                father_gender = self._get_gender_from_person(my_father)
                mother_gender = self._get_gender_from_person(my_mother)
                
                relative = obj.from_person
                
                # Side detection
                is_father_side = PersonRelation.objects.filter(
                    from_person=relative,
                    to_person=my_father
                ).exists()
                
                is_mother_side = PersonRelation.objects.filter(
                    from_person=relative,
                    to_person=my_mother
                ).exists()
                
                code = obj.relation.relation_code

                derived_map = {
                    "FATHER_SIDE": {
                        "ELDER_BROTHER": {"ta": "பெரியப்பா", "en": "Uncle"},
                        "YOUNGER_BROTHER": {"ta": "சித்தப்பா", "en": "Uncle"},
                        "BROTHER": {"ta": "சித்தப்பா", "en": "Uncle"},
                        "ELDER_SISTER": {"ta": "அத்தை", "en": "Aunt"},
                        "YOUNGER_SISTER": {"ta": "அத்தை", "en": "Aunt"},
                        "FATHER": {"ta": "தாத்தா", "en": "Grandfather"},
                        "MOTHER": {"ta": "பாட்டி", "en": "Grandmother"},
                        "WIFE": {"ta": "அம்மா", "en": "Mother"}
                    },
                    "MOTHER_SIDE": {
                        "ELDER_BROTHER": {"ta": "மாமா", "en": "Uncle"},
                        "YOUNGER_BROTHER": {"ta": "மாமா", "en": "Uncle"},
                        "YOUNGER_SISTER": {"ta": "சித்தி", "en": "Aunt"},
                        "ELDER_SISTER": {"ta": "பெரியம்மா", "en": "Aunt"},
                        "FATHER": {"ta": "தாத்தா", "en": "Grandfather"},
                        "MOTHER": {"ta": "பாட்டி", "en": "Grandmother"},
                        "HUSBAND": {"ta": "அப்பா", "en": "Father"},
                    }
                }

                if is_father_side and code in derived_map["FATHER_SIDE"]:
                    derived_label = derived_map["FATHER_SIDE"][code][language]
                    base["user_label"] = derived_label
                    base["source"] = "derived_father_side"
                    base["arrow_label"] = derived_label
                    return base

                elif is_mother_side and code in derived_map["MOTHER_SIDE"]:
                    derived_label = derived_map["MOTHER_SIDE"][code][language]
                    base["user_label"] = derived_label
                    base["source"] = "derived_mother_side"
                    base["arrow_label"] = derived_label
                    return base
        
        # Default case: relation doesn't involve me
        # Show from from_person's perspective
        base['user_label'] = self._get_base_labels(relation_code, language)
        base['arrow_label'] = self._get_perspective_arrow_label(
            relation_code, from_gender, to_gender,
            viewer_is_from=True, language=language
        )
        
        return base
    
    def get_brick_person_id(self, obj):
        """Determine which person is the 'brick' (primary person being viewed)."""
        request = self.context.get('request')
        me = self.context.get('me')
        
        if obj.to_person == me:
            # Relation to me: from_person is the brick (other person)
            return obj.from_person.id
        elif obj.from_person == me:
            # Relation from me: to_person is the brick (other person)
            return obj.to_person.id
        else:
            # Default: the "from" person is the brick
            return obj.from_person.id
    
    def get_brick_person_name(self, obj):
        """Get the name of the brick person."""
        request = self.context.get('request')
        me = self.context.get('me')
        
        if obj.to_person == me:
            return obj.from_person.full_name
        elif obj.from_person == me:
            return obj.to_person.full_name
        else:
            return obj.from_person.full_name
    
    def get_brick_person_gender(self, obj):
        """Get gender of brick person."""
        request = self.context.get('request')
        me = self.context.get('me')
        
        brick_person = None
        if obj.to_person == me:
            brick_person = obj.from_person
        elif obj.from_person == me:
            brick_person = obj.to_person
        else:
            brick_person = obj.from_person
        
        return self._get_gender_from_person(brick_person)
    
    def get_brick_label(self, obj):
        """Get the label for the brick (what appears on the node)."""
        label_data = self.get_relation_label(obj)
        return label_data.get('user_label') or label_data.get('label', '')
    
    def get_arrow_label(self, obj):
        """Get the arrow label showing relationship from viewer's perspective."""
        label_data = self.get_relation_label(obj)
        arrow_label = label_data.get('arrow_label')
        
        # If we have a custom arrow label, use it
        if arrow_label:
            return arrow_label
        
        # Fallback: generate arrow label
        request = self.context.get('request')
        me = self.context.get('me')
        
        language = 'en'
        if request and request.user.is_authenticated and hasattr(request.user, 'profile'):
            language = request.user.profile.preferred_language or 'en'
        
        # Get genders
        from_gender = self._get_gender_from_person(obj.from_person)
        to_gender = self._get_gender_from_person(obj.to_person)
        relation_code = obj.relation.relation_code
        
        # Determine viewer's perspective
        if obj.to_person == me:
            # I'm the receiver
            my_gender = to_gender
            other_gender = from_gender
            viewer_is_from = False
        elif obj.from_person == me:
            # I'm the sender
            my_gender = from_gender
            other_gender = to_gender
            viewer_is_from = True
        else:
            # Neutral: show from from_person's perspective
            my_gender = from_gender
            other_gender = to_gender
            viewer_is_from = True
        
        # Generate arrow label from viewer's perspective
        return self._get_perspective_arrow_label(
            relation_code, my_gender, other_gender,
            viewer_is_from, language
        )
    
    def get_conflicts(self, obj):
        """Get conflicts for this relation."""
        if obj.status == 'conflicted':
            return obj.conflict_reason.split('; ')
        
        # Check for potential conflicts
        conflicts = ConflictDetectionService.detect_conflicts(
            obj.from_person_id,
            obj.to_person_id,
            obj.relation.relation_code
        )
        return conflicts
    
    def validate(self, data):
        """Validate relation data."""
        request = self.context.get('request')
        
        # Set created_by
        data['created_by'] = request.user
        
        # Check permissions
        from_person = data.get('from_person') or self.instance.from_person if self.instance else None
        if from_person and from_person.linked_user != request.user:
            raise serializers.ValidationError({
                'from_person': 'You can only create relations from your own person record'
            })
        
        # Check if persons are in same family
        to_person = data.get('to_person') or self.instance.to_person if self.instance else None
        if from_person and to_person and from_person.family != to_person.family:
            raise serializers.ValidationError({
                'to_person': 'Persons must be in the same family'
            })
        
        # Check gender compatibility
        if 'relation' in data and from_person and to_person:
            relation_code = data['relation'].relation_code
            
            # Get genders
            from_gender = from_person.gender
            to_gender = to_person.gender
            
            # Use our simple validation
            is_valid = self._validate_gender_compatibility_simple(
                relation_code, from_gender, to_gender
            )
            
            if not is_valid:
                # Provide helpful error message
                error_map = {
                    'SON': 'Son must be male. Parent can be male or female.',
                    'DAUGHTER': 'Daughter must be female. Parent can be male or female.',
                    'FATHER': 'Father must be male. Child can be male or female.',
                    'MOTHER': 'Mother must be female. Child can be male or female.',
                    'HUSBAND': 'Husband must be male and wife must be female.',
                    'WIFE': 'Wife must be female and husband must be male.',
                    'SPOUSE': 'Spouses must be of opposite genders.',
                    'ELDER_BROTHER': 'Elder brother must be male.',
                    'YOUNGER_BROTHER': 'Younger brother must be male.',
                    'ELDER_SISTER': 'Elder sister must be female.',
                    'YOUNGER_SISTER': 'Younger sister must be female.',
                }
                
                error_msg = error_map.get(relation_code, 
                                        f'Gender incompatible for relation {relation_code}. '
                                        f'From: {from_gender}, To: {to_gender}')
                
                raise serializers.ValidationError({
                    'relation': error_msg
                })
        
        # Detect conflicts
        if from_person and to_person and 'relation' in data:
            conflicts = ConflictDetectionService.detect_conflicts(
                from_person.id,
                to_person.id,
                data['relation'].relation_code
            )
            
            if conflicts:
                data['status'] = 'conflicted'
                data['conflict_reason'] = '; '.join(conflicts)
        
        return data
    # In PersonRelationSerializer class
    def _validate_gender_compatibility(self, relation_code, from_gender, to_gender):
        """Custom gender compatibility validation with better error messages."""
        # Define which relations require specific gender combinations
        GENDER_RULES = {
            'SON': {
                'valid_combinations': [
                    ('M', 'M'),  # Father → Son
                    ('F', 'M'),  # Mother → Son
                ],
                'error_message': 'Son must be male and can have either male or female parent'
            },
            'DAUGHTER': {
                'valid_combinations': [
                    ('M', 'F'),  # Father → Daughter
                    ('F', 'F'),  # Mother → Daughter
                ],
                'error_message': 'Daughter must be female and can have either male or female parent'
            },
            'FATHER': {
                'valid_combinations': [
                    ('M', 'M'),  # Father → Son
                    ('M', 'F'),  # Father → Daughter
                ],
                'error_message': 'Father must be male and can have either son or daughter'
            },
            'MOTHER': {
                'valid_combinations': [
                    ('F', 'M'),  # Mother → Son
                    ('F', 'F'),  # Mother → Daughter
                ],
                'error_message': 'Mother must be female and can have either son or daughter'
            },
            'HUSBAND': {
                'valid_combinations': [
                    ('M', 'F'),  # Husband → Wife
                ],
                'error_message': 'Husband must be male and wife must be female'
            },
            'WIFE': {
                'valid_combinations': [
                    ('F', 'M'),  # Wife → Husband
                ],
                'error_message': 'Wife must be female and husband must be male'
            },
        }
        
        if relation_code in GENDER_RULES:
            combination = (from_gender, to_gender)
            if combination not in GENDER_RULES[relation_code]['valid_combinations']:
                return False, GENDER_RULES[relation_code]['error_message']
        
        return True, None
    
    # In PersonRelationSerializer class, add this method:
    def _validate_gender_compatibility_simple(self, relation_code, from_gender, to_gender):
        """Simple gender compatibility validation that makes sense."""
        
        # Allow any gender for these relations (they're generic)
        generic_relations = ['BROTHER', 'SISTER', 'SIBLING', 'PARTNER']
        
        if relation_code in generic_relations:
            return True
        
        # Define specific gender rules
        if relation_code == 'SON':
            # SON: Parent (any gender) → Child (must be male)
            return to_gender == 'M'  # Child must be male
        
        elif relation_code == 'DAUGHTER':
            # DAUGHTER: Parent (any gender) → Child (must be female)
            return to_gender == 'F'  # Child must be female
        
        elif relation_code == 'FATHER':
            # FATHER: Father (must be male) → Child (any gender)
            return from_gender == 'M'  # Parent must be male
        
        elif relation_code == 'MOTHER':
            # MOTHER: Mother (must be female) → Child (any gender)
            return from_gender == 'F'  # Parent must be female
        
        elif relation_code == 'HUSBAND':
            # HUSBAND: Husband (must be male) → Wife (must be female)
            return from_gender == 'M' and to_gender == 'F'
        
        elif relation_code == 'WIFE':
            # WIFE: Wife (must be female) → Husband (must be male)
            return from_gender == 'F' and to_gender == 'M'
        
        elif relation_code == 'SPOUSE':
            # SPOUSE: Must be opposite genders
            return (from_gender == 'M' and to_gender == 'F') or (from_gender == 'F' and to_gender == 'M')
        
        elif relation_code == 'ELDER_BROTHER':
            # ELDER_BROTHER: Must be male
            return from_gender == 'M'
        
        elif relation_code == 'YOUNGER_BROTHER':
            # YOUNGER_BROTHER: Must be male
            return from_gender == 'M'
        
        elif relation_code == 'ELDER_SISTER':
            # ELDER_SISTER: Must be female
            return from_gender == 'F'
        
        elif relation_code == 'YOUNGER_SISTER':
            # YOUNGER_SISTER: Must be female
            return from_gender == 'F'
        
        # Default: allow anything
        return True


class CreatePersonRelationSerializer(serializers.Serializer):
    """Serializer for creating person relations."""
    
    from_person_id = serializers.IntegerField(required=True)
    to_person_id = serializers.IntegerField(required=True)
    relation_code = serializers.CharField(required=True, max_length=50)
    
    def validate(self, data):
        request = self.context.get('request')
        
        # Get persons
        try:
            from_person = Person.objects.get(id=data['from_person_id'])
            to_person = Person.objects.get(id=data['to_person_id'])
        except Person.DoesNotExist:
            raise serializers.ValidationError("Person not found")
        
        # Get relation
        try:
            relation = FixedRelation.objects.get(relation_code=data['relation_code'])
        except FixedRelation.DoesNotExist:
            raise serializers.ValidationError(f"Invalid relation code: {data['relation_code']}")
        
        # Check permissions
        if from_person.linked_user and from_person.linked_user != request.user:
            raise serializers.ValidationError(
                "You can only create relations from your own person record"
            )
        
        # Check if persons are in same family
        if from_person.family != to_person.family:
            raise serializers.ValidationError("Persons must be in the same family")
        
        # Check gender compatibility
        is_valid = RelationLabelService.validate_gender_compatibility(
            relation.relation_code,
            from_person.gender,
            to_person.gender
        )
        if not is_valid:
            raise serializers.ValidationError(
                f"Gender incompatible for relation {relation.relation_code}"
            )
        
        data['from_person'] = from_person
        data['to_person'] = to_person
        data['relation'] = relation
        
        return data
    
    def create(self, validated_data):
        """Create the person relation."""
        request = self.context.get('request')
        
        # Check for existing relation
        existing = PersonRelation.objects.filter(
            from_person=validated_data['from_person'],
            to_person=validated_data['to_person'],
            relation=validated_data['relation']
        ).first()
        
        if existing:
            return existing
        
        # Create new relation
        person_relation = PersonRelation.objects.create(
            from_person=validated_data['from_person'],
            to_person=validated_data['to_person'],
            relation=validated_data['relation'],
            created_by=request.user
        )
        
        return person_relation


class ConnectedPersonsRequestSerializer(serializers.Serializer):
    """Serializer for requesting connected persons."""
    
    person_id = serializers.IntegerField(required=True)
    max_depth = serializers.IntegerField(default=3, min_value=1, max_value=10)
    include_relations = serializers.BooleanField(default=True)


class TreeViewSerializer(serializers.Serializer):
    """Serializer for family tree view."""
    
    center_person_id = serializers.IntegerField(required=True)
    max_depth = serializers.IntegerField(default=3, min_value=1, max_value=5)
    include_placeholders = serializers.BooleanField(default=True)


class AddRelativeSerializer(serializers.Serializer):
    """
    Serializer for adding relatives with AUTO-GENDER feature.
    
    When user selects:
    - 'father' → gender auto-set to 'M'
    - 'mother' → gender auto-set to 'F'
    - etc.
    """
    
    # Required fields
    full_name = serializers.CharField(max_length=200, required=True)
    
    relation_to_me = serializers.ChoiceField(
        choices=[
            ('FATHER', 'Father'),
            ('MOTHER', 'Mother'),
            ('SON', 'Son'),
            ('DAUGHTER', 'Daughter'),
            ('HUSBAND', 'Husband'),
            ('WIFE', 'Wife'),
            ('ELDER_BROTHER', 'Brother'),
            ('YOUNGER_BROTHER', 'Brother'),
            ('BROTHER', 'Brother'),
            ('SISTER', 'Sister'),
            ('ELDER_SISTER', 'Sister'),
            ('YOUNGER_SISTER', 'Sister'),
            ('SPOUSE', 'Spouse'),
            ('PARTNER', 'Partner'),
            ('CHILD', 'Child'),
            ('PARENT', 'Parent'),
        ],
        required=True,
        help_text="Relation to current user. For specific relations, gender is auto-set."
    )
    
    # Gender is optional - will be auto-set for clear relations
    gender = serializers.ChoiceField(
        choices=Person.GENDER_CHOICES,
        required=False,
        help_text="Optional. Will be auto-set for father/mother/son/daughter/etc."
    )
    
    # Optional fields
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    date_of_death = serializers.DateField(required=False, allow_null=True)
    
    def validate(self, attrs):
        """Auto-set gender based on relation_to_me - more flexible approach."""
        request = self.context.get('request')
        relation_to_me = attrs.get('relation_to_me')
        user_provided_gender = attrs.get('gender')
        
        # Simple gender mapping based on relation type only (not user's gender)
        RELATION_GENDER_MAP = {
            'FATHER': 'M',           # Father is always Male
            'MOTHER': 'F',           # Mother is always Female
            'SON': 'M',              # Son is always Male
            'DAUGHTER': 'F',         # Daughter is always Female
            'HUSBAND': 'M',          # Husband is always Male (regardless of user's gender)
            'WIFE': 'F',             # Wife is always Female (regardless of user's gender)
            'BROTHER': 'M',          # Brother is always Male
            'ELDER_BROTHER': 'M',    # Elder Brother is always Male
            'YOUNGER_BROTHER': 'M',  # Younger Brother is always Male
            'SISTER': 'F',           # Sister is always Female
            'ELDER_SISTER': 'F',     # Elder Sister is always Female
            'YOUNGER_SISTER': 'F',   # Younger Sister is always Female
            'SPOUSE': None,          # Spouse gender depends on preference
            'PARTNER': None,         # Partner can be any gender
            'CHILD': None,           # Child gender must be specified
            'PARENT': None,          # Parent gender must be specified
        }
        
        relation_to_me_upper = relation_to_me.upper()
        
        if relation_to_me_upper in RELATION_GENDER_MAP:
            auto_gender = RELATION_GENDER_MAP[relation_to_me_upper]
            
            if auto_gender is None:
                # Need manual gender selection
                if not user_provided_gender:
                    raise serializers.ValidationError({
                        'gender': f'Please specify gender for {relation_to_me.lower()}'
                    })
                # Use user-provided gender
            else:
                # Auto-set gender based on relation type
                # If user provided gender, use it (allows overrides for special cases)
                if user_provided_gender:
                    attrs['gender'] = user_provided_gender
                else:
                    attrs['gender'] = auto_gender
        else:
            # Unknown relation, require gender
            if not user_provided_gender:
                raise serializers.ValidationError({
                    'gender': f'Please specify gender for {relation_to_me.lower()}'
                })
        
        return attrs
    
    def _get_gender_display(self, gender_code):
        """Convert gender code to display text."""
        gender_map = {'M': 'Male', 'F': 'Female', 'O': 'Other'}
        return gender_map.get(gender_code, gender_code)
    
    def create(self, validated_data):
        """
        Create person and relation in one transaction.
        This method is called by the view.
        """
        # This is a serializer-level create, actual creation happens in view
        return validated_data