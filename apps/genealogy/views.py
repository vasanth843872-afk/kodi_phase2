from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
import traceback 
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import ValidationError as DRFValidationError
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import RetrieveAPIView
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from apps.relations.models import FixedRelation
from .models import Person, PersonRelation, Invitation
from .serializers import (
    PersonSerializer,
    PersonRelationSerializer,
    CreatePersonRelationSerializer,
    ConnectedPersonsRequestSerializer,
    TreeViewSerializer,
    AddRelativeSerializer
)
from apps.relations.services import RelationLabelService
from django.db import transaction
from django.contrib.auth import get_user_model
import secrets
from apps.relations.services import resolve_relation_to_me
from apps.relations.services import RelationLabelService, AshramamLabelService


class PersonViewSet(viewsets.ModelViewSet):
    """ViewSet for Person operations with generation tracking."""
    serializer_class = PersonSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def _sync_person_with_profile(self, person):
        """Sync person gender with user profile gender."""
        if person.linked_user and hasattr(person.linked_user, 'profile'):
            profile_gender = getattr(person.linked_user.profile, 'gender', None)
            if profile_gender and person.gender != profile_gender:
                # Update person gender to match profile
                person.gender = profile_gender
                person.save(update_fields=['gender'])
                print(f"Synced {person.full_name} gender from profile: {profile_gender}")
        return person

    @action(detail=True, methods=['post'])
    def sync_with_profile(self, request, pk=None):
        """Manually sync person record with user profile."""
        person = self.get_object()
        self._sync_person_with_profile(person)
        
        return Response({
            'success': True,
            'message': f'Synced {person.full_name} with profile',
            'person_gender': person.gender,
            'profile_gender': getattr(person.linked_user.profile, 'gender', None) if person.linked_user else None
        })
    
    def _get_user_display_name(self, user):
        """Get user's display name from profile or mobile number."""
        if hasattr(user, 'profile') and user.profile.firstname:
            return user.profile.firstname.strip()
        elif user.mobile_number:
            return user.mobile_number
        else:
            return f"User_{user.id}"
    
    def get_queryset(self):
        user = self.request.user
        user_person = Person.objects.filter(linked_user=user).first()
        if not user_person:
            return Person.objects.none()

        return Person.objects.filter(
            family=user_person.family
        ).select_related(
            'linked_user', 'linked_user__profile', 'family'
        )
    
    def get_serializer_context(self):
        """Add request and 'me' to serializer context."""
        context = super().get_serializer_context()
        context['request'] = self.request
        
        # Add current user's person for generation calculation
        me = Person.objects.filter(linked_user=self.request.user).first()
        if me:
            context['me'] = me
            
        return context
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's person record with generation info."""
        try:
            person = Person.objects.get(linked_user=request.user)
            serializer = self.get_serializer(person)
            return Response(serializer.data)
        except Person.DoesNotExist:
            return Response(
                {'detail': 'Person record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    # NEW GENERATION ENDPOINTS
    
    @action(detail=True, methods=['get'])
    def generation_info(self, request, pk=None):
        """Get detailed generation information and member counts."""
        person = self.get_object()
        
        # Get current user's person
        me = Person.objects.filter(linked_user=request.user).first()
        
        # Calculate generation using serializer method
        serializer = self.get_serializer(person)
        generation = serializer.get_generation(person)
        
        # ✅ FIX: Handle None generation properly
        generation_label = self._get_generation_label_for_number(generation) if generation is not None else "Not in direct lineage"
        
        # Get member counts
        immediate_family_count = serializer.get_immediate_family_count(person)
        total_connected_count = serializer.get_total_connected_count(person)
        
        # Get generation description
        generation_desc = self._get_generation_description(generation)
        
        # Get relationship info if not self
        relation_info = None
        if person != me:
            relation_info = self._get_relation_to_me(me, person)
        
        return Response({
            'person': {
                'id': person.id,
                'name': person.full_name,
                'gender': person.gender,
                'is_current_user': person == me
            },
            'generation': {
                'number': generation,
                'label': generation_label,
                'description': generation_desc,
                'level': self._get_generation_level(generation)
            },
            'member_counts': {
                'immediate_family': immediate_family_count,
                'total_connected': total_connected_count,
                'extended_family': total_connected_count - immediate_family_count
            },
            'relationship': relation_info,
            'viewer': {
                'id': me.id if me else None,
                'name': me.full_name if me else None,
                'generation': 0
            }
    })
    
    def _get_generation_description(self, generation):
        """Get detailed description of generation."""
        if generation is None:
            return "This person is not in your direct lineage"
        
        if generation == 0:
            return "This is you - the current generation"
        elif generation > 0:
            if generation == 1:
                return "This is your parent - 1 generation above you"
            elif generation == 2:
                return "This is your grandparent - 2 generations above you"
            else:
                return f"This is your ancestor - {generation} generations above you"
        else:
            if generation == -1:
                return "This is your child - 1 generation below you"
            elif generation == -2:
                return "This is your grandchild - 2 generations below you"
            else:
                return f"This is your descendant - {abs(generation)} generations below you"
    
    def _get_generation_level(self, generation):
        """Get generation level for display purposes."""
        if generation is None:
            return "unrelated"
        
        if generation == 0:
            return "self"
        elif generation > 0:
            return "ancestor"
        else:
            return "descendant"
    
    def _get_relation_to_me(self, me, other):
        """Get relation of other person to me."""
        if not me or not other:
            return None
        
        if me == other:
            return {'code': 'SELF', 'label': 'You'}
        
        # Check direct relation
        relation = PersonRelation.objects.filter(
            Q(from_person=me, to_person=other) | 
            Q(from_person=other, to_person=me),
            status__in=['confirmed', 'pending']
        ).select_related('relation').first()
        
        if relation:
            if relation.from_person == me:
                return {
                    'code': relation.relation.relation_code,
                    'label': relation.relation.default_english,
                    'direction': 'my_relation_to_them'
                }
            else:
                # Get inverse relation
                inverse_code = self._get_inverse_relation_code(
                    relation.relation.relation_code,
                    me.gender,
                    other.gender
                )
                return {
                    'code': inverse_code,
                    'label': self._get_relation_label(inverse_code),
                    'direction': 'their_relation_to_me'
                }
        
        return {'code': 'RELATED', 'label': 'Related', 'direction': 'indirect'}
    
    def _get_inverse_relation_code(self, relation_code, my_gender, other_gender):
        """Get inverse relation code."""
        INVERSE_MAP = {
            'FATHER': 'CHILD',
            'MOTHER': 'CHILD',
            'SON': 'PARENT',
            'DAUGHTER': 'PARENT',
            'HUSBAND': 'WIFE',
            'WIFE': 'HUSBAND',
            'BROTHER': 'SIBLING',
            'SISTER': 'SIBLING',
            'SPOUSE': 'SPOUSE',
            'ELDER_BROTHER': 'SIBLING',
            'YOUNGER_BROTHER': 'SIBLING',
            'ELDER_SISTER': 'SIBLING',
            'YOUNGER_SISTER': 'SIBLING',
        }
        
        inverse = INVERSE_MAP.get(relation_code, relation_code)
        
        # Refine based on gender
        if inverse == 'CHILD':
            return 'SON' if my_gender == 'M' else 'DAUGHTER'
        elif inverse == 'PARENT':
            return 'FATHER' if other_gender == 'M' else 'MOTHER'
        elif inverse == 'SIBLING':
            return 'BROTHER' if my_gender == 'M' else 'SISTER'
        
        return inverse
    
    def _get_relation_label(self, relation_code):
        """Get human-readable relation label."""
        labels = {
            'FATHER': 'Father',
            'MOTHER': 'Mother',
            'SON': 'Son',
            'DAUGHTER': 'Daughter',
            'HUSBAND': 'Husband',
            'WIFE': 'Wife',
            'BROTHER': 'Brother',
            'SISTER': 'Sister',
            'SPOUSE': 'Spouse',
            'ELDER_BROTHER': 'Elder Brother',
            'YOUNGER_BROTHER': 'Younger Brother',
            'ELDER_SISTER': 'Elder Sister',
            'YOUNGER_SISTER': 'Younger Sister',
        }
        return labels.get(relation_code, relation_code)
    
    @action(detail=True, methods=['get'])
    def generation_summary(self, request, pk=None):
        """Get summary of generations and member counts for a person."""
        person = self.get_object()
        me = Person.objects.filter(linked_user=request.user).first()
        
        if not me:
            return Response({'error': 'User has no person profile'}, status=400)
        
        # Get all persons in the same family
        family_members = Person.objects.filter(family=person.family)
        
        # Group by generation
        generations = {}
        
        for member in family_members:
            generation = self._calculate_generation(member, person)
            
            if generation is not None:
                if generation not in generations:
                    generations[generation] = {
                        'generation': generation,
                        'label': self._get_generation_label_for_number(generation),
                        'count': 0,
                        'members': []
                    }
                
                generations[generation]['count'] += 1
                
                # Get member info
                member_info = {
                    'id': member.id,
                    'name': member.full_name,
                    'gender': member.gender,
                    'is_current_user': member == person,
                    'relation': self._get_relation_to_person(member, person)
                }
                
                generations[generation]['members'].append(member_info)
        
        # Sort generations
        sorted_generations = sorted(generations.values(), key=lambda x: x['generation'])
        
        # Calculate statistics
        total_members = family_members.count()
        generation_count = len(generations)
        
        # Find oldest and youngest generations
        if generations:
            oldest_gen = min(generations.keys())
            youngest_gen = max(generations.keys())
        else:
            oldest_gen = youngest_gen = 0
        
        # Get member counts for the person being viewed
        serializer = self.get_serializer(person)
        immediate_family_count = serializer.get_immediate_family_count(person)
        total_connected_count = serializer.get_total_connected_count(person)
        
        return Response({
            'center_person': {
                'id': person.id,
                'name': person.full_name,
                'generation': 0,
                'generation_label': 'Current Generation'
            },
            'generations': sorted_generations,
            'statistics': {
                'total_family_members': total_members,
                'generation_count': generation_count,
                'oldest_generation': oldest_gen,
                'youngest_generation': youngest_gen,
                'generation_span': abs(youngest_gen - oldest_gen) + 1 if generations else 0
            },
            'member_counts': {
                'immediate_family': immediate_family_count,
                'total_connected': total_connected_count,
                'family_members': total_members
            },
            'viewer_info': {
                'viewer_person_id': me.id,
                'viewer_generation': self._calculate_generation(me, person),
                'viewer_relation': self._get_relation_to_person(me, person)
            }
        })
    
    def _calculate_generation(self, person, reference_person):
        """Calculate generation number between two persons."""
        if person == reference_person:
            return 0
        
        # Check if person is ancestor of reference person
        generation = self._find_ancestor_generation(person, reference_person)
        if generation is not None:
            return generation
        
        # Check if person is descendant of reference person
        generation = self._find_descendant_generation(person, reference_person)
        if generation is not None:
            return generation * -1
        
        return None
    
    def _find_ancestor_generation(self, ancestor, person, max_depth=10, current_depth=0, visited=None):
        """Find how many generations above the person the ancestor is."""
        if visited is None:
            visited = set()
        
        # Avoid infinite recursion
        if current_depth > max_depth:
            return None
        
        if person.id in visited:
            return None
        
        visited.add(person.id)
        
        if ancestor == person:
            return current_depth
        
        # Get direct parents of current person
        # Look for relations where person is the child (to_person)
        parent_relations = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['FATHER', 'MOTHER'],
            status__in=['confirmed', 'pending']
        ).select_related('from_person')
        
        for rel in parent_relations:
            parent = rel.from_person
            result = self._find_ancestor_generation(ancestor, parent, max_depth, current_depth + 1, visited)
            if result is not None:
                return result
        
        # Also check if person is listed as parent to someone (reverse direction)
        # This is for the case where the relationship might be stored backwards
        child_relations = PersonRelation.objects.filter(
            from_person=person,
            relation__relation_code__in=['SON', 'DAUGHTER'],
            status__in=['confirmed', 'pending']
        ).select_related('to_person')
        
        for rel in child_relations:
            child = rel.to_person
            # If person is parent to child, then ancestor would be grandparent to child
            # So we need to go DOWN one generation
            result = self._find_ancestor_generation(ancestor, child, max_depth, current_depth - 1, visited)
            if result is not None:
                return result
        
        return None
    
    def _find_descendant_generation(self, descendant, person, max_depth=10, current_depth=0, visited=None):
        """Find how many generations below the person the descendant is."""
        if visited is None:
            visited = set()
        
        # Avoid infinite recursion
        if current_depth > max_depth:
            return None
        
        if person.id in visited:
            return None
        
        visited.add(person.id)
        
        if descendant == person:
            return current_depth
        
        # Get children of current person
        children = PersonRelation.objects.filter(
            from_person=person,
            relation__relation_code__in=['SON', 'DAUGHTER'],
            status__in=['confirmed', 'pending']
        ).select_related('to_person')
        
        for child_rel in children:
            child = child_rel.to_person
            result = self._find_descendant_generation(descendant, child, max_depth, current_depth + 1, visited)
            if result is not None:
                return result
        
        # Also check reverse direction (if someone lists this person as child)
        parent_relations = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['SON', 'DAUGHTER'],
            status__in=['confirmed', 'pending']
        ).select_related('from_person')
        
        for rel in parent_relations:
            parent = rel.from_person
            # If person is child to parent, then descendant would be grandchild to parent
            result = self._find_descendant_generation(descendant, parent, max_depth, current_depth - 1, visited)
            if result is not None:
                return result
        
        return None
        
    def _get_generation_label_for_number(self, generation):
        """Get label for a specific generation number."""
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
    
    def _get_inverse_relation_code_for_person(self, relation_code, from_gender, to_gender):
        """Get inverse relation code for two persons."""
        INVERSE_MAP = {
            'FATHER': {'M': 'SON', 'F': 'DAUGHTER'},
            'MOTHER': {'M': 'SON', 'F': 'DAUGHTER'},
            'SON': {'M': 'FATHER', 'F': 'MOTHER'},
            'DAUGHTER': {'M': 'FATHER', 'F': 'MOTHER'},
            'HUSBAND': {'F': 'WIFE'},
            'WIFE': {'M': 'HUSBAND'},
        }
        
        if relation_code in INVERSE_MAP:
            gender_map = INVERSE_MAP[relation_code]
            if to_gender in gender_map:
                return gender_map[to_gender]
        
        return f"INVERSE_{relation_code}"
    
    # EXISTING METHODS FROM YOUR CODE (with small enhancements)
    
    @action(detail=True, methods=['get'])
    def relations(self, request, pk=None):
        """Get relations for a person with generation info."""
        person = self.get_object()
        
        # Get the viewer's person (ALWAYS, even if viewing someone else's page)
        me = Person.objects.filter(linked_user=request.user).first()
        
        # If viewer doesn't have a person, they can't see proper labels
        if not me:
            return Response({
                'outgoing': [],
                'incoming': [],
                'error': 'You need to create your person profile first'
            })
        
        # Get outgoing relations
        outgoing = PersonRelation.objects.filter(
            from_person=person,
            status='confirmed'
        ).select_related('to_person', 'relation')
        
        # Get incoming relations
        incoming = PersonRelation.objects.filter(
            to_person=person,
        ).select_related('from_person', 'relation')
        
        # CRITICAL: Pass BOTH 'me' AND 'viewing_person' in context
        context = {
            'request': request,
            'me': me,                     # The person making the request (viewer)
            'viewing_person': person      # Whose page we're viewing
        }
        
        # Get generation info
        serializer = self.get_serializer(person)
        generation = serializer.get_generation(person)
        generation_label = serializer.get_generation_label(person)
        
        data = {
            'outgoing': PersonRelationSerializer(outgoing, many=True, context=context).data,
            'incoming': PersonRelationSerializer(incoming, many=True, context=context).data,
            'generation_info': {
                'generation': generation,
                'generation_label': generation_label,
                'description': self._get_generation_description(generation)
            },
            'member_counts': {
                'immediate_family': serializer.get_immediate_family_count(person),
                'total_connected': serializer.get_total_connected_count(person)
            }
        }
        
        return Response(data)
    
    @action(detail=True, methods=['get'])
    def connected(self, request, pk=None):
        """Get connected persons."""
        person = self.get_object()
        
        serializer = ConnectedPersonsRequestSerializer(data=request.query_params)
        if serializer.is_valid():
            data = serializer.validated_data
            
            connected = person.get_connected_persons(max_depth=data['max_depth'])
            
            # Get person details
            person_ids = [item['person_id'] for item in connected]
            persons = Person.objects.filter(id__in=person_ids).select_related(
                'linked_user', 'linked_user__profile'
            )
            
            person_map = {p.id: p for p in persons}
            
            result = []
            for item in connected:
                person_obj = person_map.get(item['person_id'])
                if person_obj:
                    result.append({
                        'person': PersonSerializer(person_obj, context={'request': request}).data,
                        'relation_code': item['relation_code'],
                        'depth': item['depth'],
                        'is_reverse': item.get('is_reverse', False)
                    })
            
            return Response({
                'center_person': PersonSerializer(person, context={'request': request}).data,
                'connected_persons': result,
                'total_count': len(result)
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['put'])
    def update_name(self, request, pk=None):
        """
        OPTION A: Edit placeholder name.
        """
        person = self.get_object()
        
        if not self._user_in_same_family(request.user, person):
            raise PermissionDenied("You cannot edit this person")
        
        new_name = request.data.get('name')
        if not new_name:
            return Response(
                {'error': 'Name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        person.full_name = new_name
        person.save()
        
        return Response({
            'success': True,
            'message': 'Name updated successfully',
            'new_name': new_name,
            'person_id': person.id
        })
    
    @action(detail=False, methods=['post'])
    def add_relative(self, request):
        """
        Add relative with AUTO-GENDER.
        Creates person and relation in one request.
        """
        relation = request.data.get("relation_to_me")
            
        serializer = AddRelativeSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Get current user's person
                current_person = self._get_or_create_current_person(request.user)
                
                # Extract data
                person_data = serializer.validated_data.copy()
                relation_to_me = person_data.pop('relation_to_me')
                target_person_id = person_data.pop('target_person_id', None)
                
                # If target_person_id is provided, add relative to that person
                # Otherwise, add relative to current user
                if target_person_id:
                    try:
                        target_person = Person.objects.get(id=target_person_id)
                        
                        # Check if user has permission to add relative to this person
                        if not self._can_add_relative_to_person(request.user, target_person):
                            raise PermissionDenied("You don't have permission to add relatives to this person")
                        
                    except Person.DoesNotExist:
                        return Response(
                            {'error': 'Target person not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )
                else:
                    target_person = current_person
                
                # Get FixedRelation object
                fixed_relation = self._get_fixed_relation(relation_to_me, person_data['gender'])
                
                # ✅ CHECK FOR DUPLICATE EXCLUSIVE RELATIONS
                exclusive_relations = ['FATHER', 'MOTHER', 'HUSBAND', 'WIFE']
                
                if relation_to_me.upper() in exclusive_relations:
                    relation_code = relation_to_me.upper()
                    
                    if relation_code in ['FATHER', 'MOTHER']:
                        # Check if target person already has this parent
                        exists = PersonRelation.objects.filter(
                            to_person=target_person,
                            relation__relation_code=relation_code,
                            status__in=['confirmed', 'pending']
                        ).exists()
                        
                        if exists:
                            return Response({
                                'error': f'{target_person.full_name} already has a {relation_code.lower()}',
                                'action': 'connect_existing',
                                'person_id': target_person.id
                            }, status=status.HTTP_400_BAD_REQUEST)
                            
                    elif relation_code in ['HUSBAND', 'WIFE']:
                        # Check if target person already has a spouse
                        exists = PersonRelation.objects.filter(
                            Q(from_person=target_person) | Q(to_person=target_person),
                            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
                            status__in=['confirmed', 'pending']
                        ).exists()
                        
                        if exists:
                            return Response({
                                'error': f'{target_person.full_name} already has a spouse',
                                'action': 'connect_existing',
                                'person_id': target_person.id
                            }, status=status.HTTP_400_BAD_REQUEST)
                
                # Create the new person
                new_person = Person.objects.create(
                    full_name=person_data['full_name'],
                    gender=person_data['gender'],
                    date_of_birth=person_data.get('date_of_birth'),
                    date_of_death=person_data.get('date_of_death'),
                    family=target_person.family,  # Same family as target person
                    linked_user=None,
                    is_alive=not bool(person_data.get('date_of_death')),
                    is_placeholder=True
                )
                
                # Determine relation direction
                if relation_to_me.upper() in ['FATHER', 'MOTHER', 'PARENT']:
                    # Parent → Target person
                    from_person = new_person
                    to_person = target_person
                    relation_direction = 'parent_to_child'
                    
                elif relation_to_me.upper() in ['SON', 'DAUGHTER', 'CHILD']:
                    # Target person → Child
                    from_person = new_person
                    to_person = target_person
                    relation_direction = 'child_to_parent'
                    
                elif relation_to_me.upper() == 'HUSBAND':
                    # Husband → Wife (target person should be female)
                    # Check if target person has gender
                    if not target_person.gender:
                        return Response({
                            'error': f'{target_person.full_name} does not have a gender specified',
                            'suggestion': 'Please set gender for this person first'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    if target_person.gender != 'F':
                        return Response({
                            'error': 'Husband can only be added to a female person',
                            'suggestion': 'Use WIFE relation for male persons or SON/DAUGHTER for children'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Also check if new person (husband) is male
                    if person_data['gender'] != 'M':
                        return Response({
                            'error': 'Husband must be male',
                            'suggestion': 'Change gender to Male for husband'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    from_person = new_person  # Husband
                    to_person = target_person  # Wife
                    relation_direction = 'spouse'
                    
                elif relation_to_me.upper() == 'WIFE':
                    # Wife → Husband (target person should be male)
                    if target_person.gender != 'M':
                        return Response({
                            'error': 'Wife can only be added to a male person',
                            'suggestion': 'Use HUSBAND relation for female persons'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    from_person = new_person  # Husband
                    to_person = target_person  # Wife
                    relation_direction = 'spouse'
                    
                elif relation_to_me.upper() in ['BROTHER', 'SISTER', 'SIBLING',
                                            'ELDER_BROTHER', 'YOUNGER_BROTHER',
                                            'ELDER_SISTER', 'YOUNGER_SISTER']:
                    # Sibling → Target person
                    from_person = new_person
                    to_person = target_person
                    relation_direction = 'sibling'
                    
                else:
                    # Default: new person → target person
                    from_person = new_person
                    to_person = target_person
                    relation_direction = 'general'
                
                # Determine relation status
                # Auto-confirm if both are placeholders in same family
                if not target_person.linked_user and not new_person.linked_user:
                    status_to_use = 'confirmed'
                    auto_confirmed = True
                else:
                    status_to_use = 'pending'
                    auto_confirmed = False
                
                # Create the relation
                try:
                    person_relation = PersonRelation.objects.create(
                        from_person=from_person,
                        to_person=to_person,
                        relation=fixed_relation,
                        status=status_to_use,
                        created_by=request.user
                    )
                except DRFValidationError as e:
                    # Handle gender validation errors
                    return Response({
                        'error': 'Gender validation failed',
                        'details': str(e),
                        'suggestion': 'Check gender compatibility'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Return success response
                response_data = {
                    'success': True,
                    'message': f"Added {new_person.full_name} as {target_person.full_name}'s {relation_to_me.lower()}",
                    'person': {
                        'id': new_person.id,
                        'full_name': new_person.full_name,
                        'gender': new_person.get_gender_display(),
                        'is_placeholder': new_person.linked_user is None,
                        'family_id': new_person.family_id
                    },
                    'target_person': {
                        'id': target_person.id,
                        'full_name': target_person.full_name,
                        'is_current_user': target_person == current_person
                    },
                    'relation': {
                        'id': person_relation.id,
                        'relation_type': fixed_relation.relation_code,
                        'relation_label': fixed_relation.default_english,
                        'status': person_relation.status,
                        'direction': f"{from_person.full_name} → {to_person.full_name}",
                        'auto_confirmed': auto_confirmed
                    },
                    'next_actions': []
                }
                
                # Suggest next actions based on the new person
                if new_person.linked_user is None:  # It's a placeholder
                    response_data['next_actions'].extend([
                        {
                            'action': 'edit_name',
                            'label': 'Edit Name',
                            'method': 'PUT',
                            'url': f'/api/persons/{new_person.id}/update_name/'
                        },
                        {
                            'action': 'connect',
                            'label': 'Connect to Real User',
                            'method': 'POST',
                            'url': f'/api/persons/{new_person.id}/send_invitation/'
                        },
                        {
                            'action': 'add_more_relatives',
                            'label': 'Add More Relatives',
                            'method': 'GET',
                            'url': f'/api/persons/{new_person.id}/next_flow/'
                        }
                    ])
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
        except PermissionDenied as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
            
        except Exception as e:
            import traceback
            error_detail = {
                'error': str(e),
                'traceback': traceback.format_exc(),
                'detail': 'Failed to add relative'
            }
            return Response(error_detail, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _can_add_relative_to_person(self, user, target_person):
        """
        Check if user can add relatives to target person.
        Returns True if:
        1. User is the target person (adding to self)
        2. Target person is in user's family and not connected to another user
        3. Target person is a placeholder not connected to any user
        """
        # Get user's person
        user_person = Person.objects.filter(linked_user=user).first()
        if not user_person:
            return False
        
        # Case 1: User is adding to themselves
        if target_person.linked_user == user:
            return True
        
        # Case 2: Target person is in user's family
        if target_person.family_id == user_person.family_id:
            # Can add if target is not connected to another user
            if target_person.linked_user is None:
                return True
            # Can add if target is connected to the same user (should be case 1)
            elif target_person.linked_user == user:
                return True
        
        # Case 3: Target person is a placeholder in different family
        if target_person.linked_user is None:
            # Check if there's a connection between users
            is_connected = PersonRelation.objects.filter(
                Q(from_person=target_person, to_person=user_person) |
                Q(from_person=user_person, to_person=target_person),
                status='confirmed'
            ).exists()
            
            # Can add if NOT connected (connected means read-only)
            return not is_connected
        
        return False
    
    @action(detail=True, methods=['post'])
    def send_invitation(self, request, pk=None):
        """Connect placeholder to real user WITH ORIGINAL RELATION."""
        person = self.get_object()
        
        if person.linked_user:
            return Response({'error': 'Person is already connected'}, status=400)
        
        contact_info = request.data.get('mobile_number')
        if not contact_info:
            return Response({'error': 'Contact information required'}, status=400)
        
        # Get current user's person
        current_person = self._get_or_create_current_person(request.user)
        
        # Find the original relation between placeholder and inviter
        original_relation = None
        
        # Look for relation FROM placeholder TO inviter
        relation_to_inviter = PersonRelation.objects.filter(
            from_person=person,
            to_person=current_person,
            status__in=['confirmed', 'pending']
        ).first()
        
        # If not found, look for relation FROM inviter TO placeholder
        if not relation_to_inviter:
            relation_to_inviter = PersonRelation.objects.filter(
                from_person=current_person,
                to_person=person,
                status__in=['confirmed', 'pending']
            ).first()
        
        if relation_to_inviter:
            original_relation = relation_to_inviter.relation
        
        User = get_user_model()
        
        try:
            # Find user
            if '@' in contact_info:
                existing_user = User.objects.get(email=contact_info)
            else:
                existing_user = User.objects.get(mobile_number=contact_info)
            
            # Check if invitation already exists
            existing_invitation = Invitation.objects.filter(
                person=person,
                invited_user=existing_user,
                status='pending'
            ).first()
            
            if existing_invitation:
                return Response({
                    'status': 'invitation_exists',
                    'message': 'Invitation already sent',
                    'invitation_id': existing_invitation.id
                })
            
            # Create invitation with ORIGINAL relation
            invitation = Invitation.objects.create(
                person=person,
                invited_user=existing_user,
                invited_by=request.user,
                token=secrets.token_urlsafe(32),
                status='pending',
                original_relation=original_relation,
                placeholder_gender=person.gender
            )
            
            print(f"INVITATION CREATED: {invitation.id}")
            print(f"TOKEN: {invitation.token}")
            print(f"ORIGINAL RELATION: {original_relation.relation_code if original_relation else 'None'}")
            
            # TODO: Send notification (implement this)
            # self._send_invitation_notification(invitation)
            
            return Response({
                'status': 'invitation_sent',
                'message': f'Invitation sent to {existing_user.mobile_number}',
                'invitation_id': invitation.id,
                'user_exists': True,
                'action_needed': 'user_must_accept',
                'original_relation': original_relation.relation_code if original_relation else None
            })
            
        except User.DoesNotExist:
            return Response({
                'status': 'no_user_found',
                'message': f'No user found with {contact_info}',
                'user_exists': False,
                'action': 'invite_to_app'
            })
    
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='accept-invitation/(?P<token>[^/.]+)',
    )
    def accept_invitation(self, request, token):
        """
        User accepts invitation - REPLACES placeholder with user's real person.
        PRESERVES ORIGINAL RELATION.
        """
        invitation = get_object_or_404(
            Invitation,
            token=token,
            status='pending'
        )
        
        if invitation.is_expired():
            invitation.status = 'expired'
            invitation.save()
            return Response({'error': 'Invitation expired'}, status=400)
        
        if invitation.invited_user != request.user:
            return Response({'error': 'This invitation is not for you'}, status=403)
        
        placeholder = invitation.person
        
        with transaction.atomic():
            # Get inviter's person (UserA)
            inviter_person = Person.objects.filter(linked_user=invitation.invited_by).first()
            
            # STEP 1: Check if user already has a person
            user_person = Person.objects.filter(linked_user=request.user).first()
            
            if user_person:
                # User already has a person record
                # We need to DELETE the user's existing person and REPLACE it with placeholder
                # But first, we need to handle all relations of the user's existing person
                
                # Get all relations of user's existing person
                user_outgoing = PersonRelation.objects.filter(from_person=user_person)
                user_incoming = PersonRelation.objects.filter(to_person=user_person)
                
                # Redirect all relations from user's person to placeholder
                for rel in user_outgoing:
                    rel.from_person = placeholder
                    rel.save()
                
                for rel in user_incoming:
                    rel.to_person = placeholder
                    rel.save()
                
                # Now delete user's existing person
                old_user_person_id = user_person.id
                user_person.delete()
                
                # Now connect placeholder to user
                placeholder.linked_user = request.user
                placeholder.is_placeholder = False
                
                # Update placeholder name to user's REAL NAME (not mobile number)
                user_display_name = self._get_user_display_name(request.user)
                
                if placeholder.full_name != user_display_name:
                    # Preserve original placeholder name as alias
                    placeholder.original_name = placeholder.full_name
                    placeholder.full_name = user_display_name
                
                placeholder.save()
                
                # Auto-confirm pending relations
                PersonRelation.objects.filter(
                    Q(from_person=placeholder) | Q(to_person=placeholder),
                    status='pending'
                ).update(status='confirmed')
                
                # ✅ CRITICAL: Create relation between inviter (UserA) and placeholder (now UserB)
                connection_created = False
                if inviter_person:
                    # Check if relation already exists
                    existing_relation = PersonRelation.objects.filter(
                        Q(from_person=placeholder, to_person=inviter_person) |
                        Q(from_person=inviter_person, to_person=placeholder)
                    ).first()
                    
                    if not existing_relation:
                        # Use ORIGINAL relation from invitation if available
                        if invitation.original_relation:
                            fixed_relation = invitation.original_relation
                            print(f"Using ORIGINAL relation: {fixed_relation.relation_code}")
                        else:
                            # Fallback: Determine relation based on placeholder gender
                            if placeholder.gender == 'F':
                                relation_code = 'SISTER'
                            elif placeholder.gender == 'M':
                                relation_code = 'BROTHER'
                            else:
                                relation_code = 'SIBLING'
                            
                            try:
                                fixed_relation = FixedRelation.objects.get(relation_code=relation_code)
                            except FixedRelation.DoesNotExist:
                                fixed_relation = FixedRelation.objects.first()
                        
                        # Create relation: UserB (placeholder) → UserA
                        PersonRelation.objects.create(
                            from_person=placeholder,  # UserB
                            to_person=inviter_person,  # UserA
                            relation=fixed_relation,
                            status='confirmed',
                            created_by=request.user
                        )
                        
                        connection_created = True
                
                # Update invitation
                invitation.status = 'accepted'
                invitation.accepted_at = timezone.now()
                invitation.save()
                
                return Response({
                    'success': True,
                    'message': f'You are now connected as "{placeholder.full_name}" (replaced placeholder)',
                    'action': 'placeholder_replaced',
                    'details': {
                        'old_person_deleted': old_user_person_id,
                        'new_person': {
                            'id': placeholder.id,
                            'name': placeholder.full_name,
                            'gender': placeholder.gender,
                            'family_id': placeholder.family_id,
                            'is_now_user': True,
                            'original_name': placeholder.original_name
                        },
                        'relations_redirected': user_outgoing.count() + user_incoming.count(),
                        'connection_created': connection_created,
                        'connected_to_inviter': inviter_person.id if inviter_person else None,
                        'relation_used': invitation.original_relation.relation_code if invitation.original_relation else 'gender_based'
                    }
                })
            else:
                # User doesn't have a person record - simply connect placeholder to user
                placeholder.linked_user = request.user
                placeholder.is_placeholder = False
                
                # Update placeholder name to user's REAL NAME (not mobile number)
                user_display_name = self._get_user_display_name(request.user)
                
                if placeholder.full_name != user_display_name:
                    # Preserve original placeholder name as alias
                    placeholder.original_name = placeholder.full_name
                    placeholder.full_name = user_display_name
                
                placeholder.save()
                
                # Auto-confirm pending relations
                PersonRelation.objects.filter(
                    Q(from_person=placeholder) | Q(to_person=placeholder),
                    status='pending'
                ).update(status='confirmed')
                
                # ✅ CRITICAL: Create relation between inviter (UserA) and placeholder (now UserB)
                connection_created = False
                if inviter_person:
                    # Check if relation already exists
                    existing_relation = PersonRelation.objects.filter(
                        Q(from_person=placeholder, to_person=inviter_person) |
                        Q(from_person=inviter_person, to_person=placeholder)
                    ).first()
                    
                    if not existing_relation:
                        # Use ORIGINAL relation from invitation if available
                        if invitation.original_relation:
                            fixed_relation = invitation.original_relation
                            print(f"Using ORIGINAL relation: {fixed_relation.relation_code}")
                        else:
                            # Fallback: Determine relation based on placeholder gender
                            if placeholder.gender == 'F':
                                relation_code = 'SISTER'
                            elif placeholder.gender == 'M':
                                relation_code = 'BROTHER'
                            else:
                                relation_code = 'SIBLING'
                            
                            try:
                                fixed_relation = FixedRelation.objects.get(relation_code=relation_code)
                            except FixedRelation.DoesNotExist:
                                fixed_relation = FixedRelation.objects.first()
                        
                        # Create relation: UserB (placeholder) → UserA
                        PersonRelation.objects.create(
                            from_person=placeholder,  # UserB
                            to_person=inviter_person,  # UserA
                            relation=fixed_relation,
                            status='confirmed',
                            created_by=request.user
                        )
                        connection_created = True
                
                # Update invitation
                invitation.status = 'accepted'
                invitation.accepted_at = timezone.now()
                invitation.save()
                
                return Response({
                    'success': True,
                    'message': f'You are now connected as "{placeholder.full_name}"',
                    'action': 'placeholder_became_user',
                    'person': PersonSerializer(placeholder, context={'request': request}).data,
                    'connection_created': connection_created,
                    'connected_to_inviter': inviter_person.id if inviter_person else None,
                    'relation_used': invitation.original_relation.relation_code if invitation.original_relation else 'gender_based',
                    'original_name': placeholder.original_name
                })
                
    def assert_can_edit_person(self, user, person):
        # Allow editing if:
        if person.is_placeholder and (person.linked_user is None or person.linked_user == user):
            return
        if person.family.created_by == user:
            return
        # Otherwise block
        raise PermissionDenied("You cannot add relatives to this person")
    
   
   
    @action(detail=True, methods=['post'])
    def add_relative_action(self, request, pk=None):
        """Handle ALL add relative actions from next flow."""
        person = get_object_or_404(Person, id=pk)
        
        # Check if person is a connected user that can't be modified
        if person.linked_user is not None and person.linked_user != request.user:
            # This is a connected user, you cannot modify their relations
            raise PermissionDenied("Cannot add relatives to a connected user")
        
        # Check if user has permission to edit this person
        self.assert_can_edit_person(request.user, person)
        
        action = request.data.get('action')
        name = request.data.get('full_name', '')  # Changed from 'name' to 'full_name'
        
        ACTION_MAP = {
            'add_father': {'code': 'FATHER', 'gender': 'M', 'direction': 'parent'},
            'add_mother': {'code': 'MOTHER', 'gender': 'F', 'direction': 'parent'},
            'add_son': {'code': 'SON', 'gender': 'M', 'direction': 'child'},
            'add_daughter': {'code': 'DAUGHTER', 'gender': 'F', 'direction': 'child'},
            'add_elder_brother': {'code': 'ELDER_BROTHER', 'gender': 'M', 'direction': 'sibling'},
            'add_younger_brother': {'code': 'YOUNGER_BROTHER', 'gender': 'M', 'direction': 'sibling'},
            'add_elder_sister': {'code': 'ELDER_SISTER', 'gender': 'F', 'direction': 'sibling'},
            'add_younger_sister': {'code': 'YOUNGER_SISTER', 'gender': 'F', 'direction': 'sibling'},
            'add_husband': {'code': 'HUSBAND', 'gender': 'M', 'direction': 'spouse'},
            'add_wife': {'code': 'WIFE', 'gender': 'F', 'direction': 'spouse'},
            'add_spouse': {'code': 'SPOUSE', 'gender': None, 'direction': 'spouse'},
            'add_partner': {'code': 'PARTNER', 'gender': None, 'direction': 'partner'},
        }
        
        if action not in ACTION_MAP:
            return Response({'error': 'Invalid action'}, status=400)
        
        action_info = ACTION_MAP[action]
        
        # Check if user can add relatives to this person
        user = request.user
        user_person = Person.objects.filter(linked_user=user).first()
        
        if not user_person:
            return Response({'error': 'User has no person profile'}, status=400)
        
        # Check if the person is in user's family (can edit/add)
        if user_person.family_id != person.family_id:
            # Not in same family - check if connected
            is_connected = PersonRelation.objects.filter(
                Q(from_person=person, to_person=user_person) |
                Q(from_person=user_person, to_person=person),
                status='confirmed'
            ).exists()
            
            if is_connected:
                # User is connected - they can only view, not add
                return Response({
                    'error': 'Cannot add relatives to connected persons from other families',
                    'permission': 'read_only'
                }, status=403)
            else:
                # Not connected and not in same family - check if person is a placeholder
                if person.linked_user is None:
                    # Person is a placeholder in different family
                    # This is where we allow adding relatives!
                    pass
                else:
                    # Person is a real user in different family - no access
                    raise PermissionDenied("You don't have access to this person")
        
        # ✅ CHECK FOR DUPLICATE EXCLUSIVE RELATIONS
        exclusive_actions = ['add_father', 'add_mother', 'add_husband', 'add_wife', 'add_spouse']
        
        if action in exclusive_actions:
            relation_code = action_info['code']
            
            if action in ['add_father', 'add_mother']:
                exists = PersonRelation.objects.filter(
                    to_person=person,
                    relation__relation_code=relation_code,
                    status__in=['confirmed', 'pending']
                ).exists()
            elif action in ['add_husband', 'add_wife', 'add_spouse']:
                exists = PersonRelation.objects.filter(
                    Q(from_person=person) | Q(to_person=person),
                    relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
                    status__in=['confirmed', 'pending']
                ).exists()
            
            if exists:
                return Response({
                    'error': f'{person.full_name} already has a {action.replace("add_", "")}',
                    'action': 'connect_existing'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # If gender not auto-set, get from request
        gender = action_info['gender']
        if gender is None:
            gender = request.data.get('gender')
            if not gender:
                return Response({'error': 'Gender required for this relation'}, status=400)
        
        # Generate name if not provided
        if not name:
            relation_name = action.replace('add_', '').title()
            name = f"{relation_name} of {person.full_name}"
        
        try:
            with transaction.atomic():
                fixed_relation = FixedRelation.objects.get(relation_code=action_info['code'])
                
                # Create new person in the SAME family as the target person
                new_person = Person.objects.create(
                    full_name=name,
                    gender=gender,
                    family=person.family,  # Same family as target person
                    linked_user=None,
                    is_placeholder=True
                )
                
                # Determine relation direction based on ACTION TYPE
                if action in ['add_father', 'add_mother']:
                    # Adding parent: new_person (parent) → person (child)
                    from_person = new_person  # Parent
                    to_person = person        # Child
                elif action in ['add_son', 'add_daughter']:
                    # Adding child: person (parent) → new_person (child)
                    from_person = person      # Parent
                    to_person = new_person    # Child
                elif action in ['add_husband', 'add_wife', 'add_spouse']:
                    # Adding spouse: new_person → person
                    from_person = new_person
                    to_person = person
                else:
                    # Siblings and others: new_person → person
                    from_person = new_person
                    to_person = person
                
                # ✅ FIXED: Manually validate gender compatibility
                # The key insight: For SON/DAUGHTER, from_person is the parent, to_person is the child
                # So we need to check if the parent's gender is compatible with the child's gender
                
                if action == 'add_son':
                    # Parent (from_person) → Son (to_person)
                    # Son must be male, parent can be male or female
                    if to_person.gender != 'M':
                        new_person.delete()
                        return Response({
                            'error': 'Son must be male',
                            'details': {
                                'child_gender': to_person.gender,
                                'expected': 'M'
                            }
                        }, status=400)
                    # Parent gender validation happens in the RelationLabelService
                    
                elif action == 'add_daughter':
                    # Parent (from_person) → Daughter (to_person)
                    # Daughter must be female, parent can be male or female
                    if to_person.gender != 'F':
                        new_person.delete()
                        return Response({
                            'error': 'Daughter must be female',
                            'details': {
                                'child_gender': to_person.gender,
                                'expected': 'F'
                            }
                        }, status=400)
                    
                elif action == 'add_father':
                    # Father (from_person) → Child (to_person)
                    # Father must be male
                    if from_person.gender != 'M':
                        new_person.delete()
                        return Response({
                            'error': 'Father must be male',
                            'details': {
                                'parent_gender': from_person.gender,
                                'expected': 'M'
                            }
                        }, status=400)
                    
                elif action == 'add_mother':
                    # Mother (from_person) → Child (to_person)
                    # Mother must be female
                    if from_person.gender != 'F':
                        new_person.delete()
                        return Response({
                            'error': 'Mother must be female',
                            'details': {
                                'parent_gender': from_person.gender,
                                'expected': 'F'
                            }
                        }, status=400)
                
                # AUTO-CONFIRM placeholder-to-placeholder relations
                status_to_use = 'confirmed' if (not person.linked_user and not new_person.linked_user) else 'pending'
                
                # Create relation
                try:
                    person_relation = PersonRelation.objects.create(
                        from_person=from_person,
                        to_person=to_person,
                        relation=fixed_relation,
                        status=status_to_use,
                        created_by=request.user
                    )
                except Exception as e:
                    # Catch validation errors
                    new_person.delete()
                    if 'Gender incompatible' in str(e):
                        return Response({
                            'error': str(e),
                            'details': {
                                'from_person_gender': from_person.gender,
                                'to_person_gender': to_person.gender,
                                'relation': fixed_relation.relation_code
                            }
                        }, status=400)
                    # Re-raise other errors
                    raise
                
                return Response({
                    'success': True,
                    'message': f"Added {name} as {action.replace('add_', '')} of {person.full_name}",
                    'new_person': {
                        'id': new_person.id,
                        'name': new_person.full_name,
                        'gender': new_person.gender,
                        'is_placeholder': True
                    },
                    'relation': {
                        'id': person_relation.id,
                        'type': fixed_relation.relation_code,
                        'status': person_relation.status,
                        'from_person_id': from_person.id,
                        'to_person_id': to_person.id
                    },
                    'direction_info': {
                        'from_person': from_person.full_name,
                        'from_gender': from_person.gender,
                        'to_person': to_person.full_name,
                        'to_gender': to_person.gender,
                        'relation': fixed_relation.relation_code
                    },
                    'next_actions': ['edit_name', 'connect', 'next_flow']
                })
            
        except Exception as e:
            return Response({'error': str(e)}, status=500) 
    @action(detail=True, methods=['get'])
    def next_flow(self, request, pk=None):
        """
        Get next flow options based on person status.
        """
        person = self.get_object()
        user = request.user
        user_person = Person.objects.filter(linked_user=user).first()
        
        if person.linked_user and person.linked_user != request.user:
            # Always read-only for other users
            return self._get_connected_person_view(person, user_person, request)
        
        if not user_person:
            return Response({'error': 'You need to create your person profile first'})
        
        # 1. Check if user OWNS this person
        is_owner = person.linked_user == user
        
        # 2. Check if in same family
        in_same_family = user_person.family_id == person.family_id
        
        # 3. Check if connected via cross-family relation
        is_connected = PersonRelation.objects.filter(
            Q(from_person=person, to_person=user_person) |
            Q(from_person=user_person, to_person=person),
            status='confirmed'
        ).exists()
        
        if is_connected:
            return self._get_connected_person_view(person, user_person, request)
        
        if is_owner:
            # User viewing their own person
            if person.linked_user:
                # This is user's own person - they can edit
                return self._get_own_person_edit_view(person, request)
            else:
                # User viewing their own placeholder (shouldn't happen)
                return self._get_placeholder_family_and_options(person, request)
        
        elif in_same_family:
            # Person is in user's family tree
            # Check if this is a placeholder that represents a connected user
            connection = PersonRelation.objects.filter(
                Q(from_person=person, to_person=user_person) |
                Q(from_person=user_person, to_person=person),
                status='confirmed'
            ).first()
            
            if connection and person.linked_user is None:
                # This placeholder REPRESENTS a connected user from another family
                return self._get_connected_person_view(person, user_person, request)
            else:
                # Regular family member - check permissions
                if is_connected:
                    # User is also connected to this person (different families)
                    return self._get_connected_person_view(person, user_person, request)
                else:
                    # User can edit this person (same family, not connected)
                    return self._get_placeholder_options(person, request)
        
        else:
            # Different families
            if is_connected:
                # User is connected - show read-only view
                return self._get_connected_person_view(person, user_person, request)
            else:
                # Not connected - check if person is a placeholder
                if person.linked_user is None:
                    # Person is a placeholder in different family
                    # User can add relatives to this placeholder!
                    return self._get_placeholder_options(person, request)
                else:
                    # Person is a real user in different family - no access
                    raise PermissionDenied("You don't have permission to view this person")
    
    def _get_own_person_edit_view(self, person, request):
        """User viewing their own person (full edit permissions)."""
        # Get existing exclusive relations
        existing_parents = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['FATHER', 'MOTHER'],
            status__in=['confirmed', 'pending']
        ).values_list('relation__relation_code', flat=True)
        
        existing_spouses = PersonRelation.objects.filter(
            Q(from_person=person) | Q(to_person=person),
            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
            status__in=['confirmed', 'pending']
        ).exists()
        
        # Build add options
        add_options = []
        
        # Add father option only if not already exists
        if 'FATHER' not in existing_parents:
            add_options.append({
                'action': 'add_father',
                'label': f"Add {person.full_name}'s Father",
                'relation_code': 'FATHER',
                'auto_gender': 'M',
                'icon': '👴'
            })
        
        # Add mother option only if not already exists
        if 'MOTHER' not in existing_parents:
            add_options.append({
                'action': 'add_mother',
                'label': f"Add {person.full_name}'s Mother",
                'relation_code': 'MOTHER',
                'auto_gender': 'F',
                'icon': '👵'
            })
        
        # Always allow children
        add_options.extend([
            {
                'action': 'add_son',
                'label': f"Add {person.full_name}'s Son",
                'relation_code': 'SON',
                'auto_gender': 'M',
                'icon': '👦'
            },
            {
                'action': 'add_daughter',
                'label': f"Add {person.full_name}'s Daughter",
                'relation_code': 'DAUGHTER',
                'auto_gender': 'F',
                'icon': '👧'
            },
        ])
        
        # Always allow siblings
        add_options.extend([
            {
                'action': 'add_elder_brother',
                'label': f"Add {person.full_name}'s Elder Brother",
                'relation_code': 'ELDER_BROTHER',
                'auto_gender': 'M',
                'icon': '👨‍🦳',
                'category': 'siblings'
            },
            {
                'action': 'add_younger_brother',
                'label': f"Add {person.full_name}'s Younger Brother",
                'relation_code': 'YOUNGER_BROTHER',
                'auto_gender': 'M',
                'icon': '👨',
                'category': 'siblings'
            },
            {
                'action': 'add_elder_sister',
                'label': f"Add {person.full_name}'s Elder Sister",
                'relation_code': 'ELDER_SISTER',
                'auto_gender': 'F',
                'icon': '👩‍🦳',
                'category': 'siblings'
            },
            {
                'action': 'add_younger_sister',
                'label': f"Add {person.full_name}'s Younger Sister",
                'relation_code': 'YOUNGER_SISTER',
                'auto_gender': 'F',
                'icon': '👩',
                'category': 'siblings'
            },
        ])
        
        # Add spouse option only if not already exists
        if not existing_spouses:
            if person.gender == 'M':
                add_options.append({
                    'action': 'add_wife',
                    'label': f"Add {person.full_name}'s Wife",
                    'relation_code': 'WIFE',
                    'auto_gender': 'F',
                    'icon': '👰'
                })
            elif person.gender == 'F':
                add_options.append({
                    'action': 'add_husband',
                    'label': f"Add {person.full_name}'s Husband",
                    'relation_code': 'HUSBAND',
                    'auto_gender': 'M',
                    'icon': '🤵'
                })
            else:
                add_options.append({
                    'action': 'add_spouse',
                    'label': f"Add {person.full_name}'s Spouse",
                    'relation_code': 'SPOUSE',
                    'auto_gender': None,
                    'icon': '💑'
                })
        
        # Get family members
        family_members = Person.objects.filter(
            family=person.family
        ).exclude(id=person.id)
        
        # Get relations
        outgoing = PersonRelation.objects.filter(
            from_person=person,
            status__in=['confirmed', 'pending']
        ).select_related('to_person', 'relation')
        
        incoming = PersonRelation.objects.filter(
            to_person=person,
            status__in=['confirmed', 'pending']
        ).select_related('from_person', 'relation')
        
        return Response({
            'status': 'own_person_edit_view',
            'view_type': 'edit_mode',
            'permissions': {
                'can_edit': True,
                'can_add_relatives': True,
                'can_delete': True,
                'is_owner': True,
                'is_in_family': True,
                'is_readonly': False
            },
            'person': PersonSerializer(person, context={'request': request}).data,
            'family_info': {
                'family_name': person.family.family_name if person.family else None,
                'family_id': person.family_id,
                'member_count': family_members.count() + 1
            },
            'existing_relations': {
                'outgoing': [
                    {
                        'person': PersonSerializer(rel.to_person, context={'request': request}).data,
                        'relation': rel.relation.relation_code if rel.relation else None,
                        'status': rel.status,
                        'direction': 'outgoing'
                    }
                    for rel in outgoing
                ],
                'incoming': [
                    {
                        'person': PersonSerializer(rel.from_person, context={'request': request}).data,
                        'relation': rel.relation.relation_code if rel.relation else None,
                        'status': rel.status,
                        'direction': 'incoming'
                    }
                    for rel in incoming
                ]
            },
            'family_members': PersonSerializer(family_members, many=True, context={'request': request}).data,
            'add_options': add_options,
            'actions': [
                {
                    'action': 'edit_name',
                    'label': 'Edit My Name',
                    'icon': '✏️',
                    'description': 'Change your display name'
                },
                {
                    'action': 'view_tree',
                    'label': 'View Family Tree',
                    'icon': '🌳',
                    'description': 'Browse family tree'
                }
            ],
            'message': 'This is your person profile. You can edit and add relatives.'
        })
    
    def _get_placeholder_options(self, person, request):
        """Show ALL family relations with auto-gender."""
        user = request.user
        user_person = Person.objects.filter(linked_user=user).first()
        viewer_person = user_person
        existing_relations_data = self._get_existing_relations(person, person)
        
        if person.linked_user and person.linked_user != request.user:
            user_person = Person.objects.filter(linked_user=request.user).first()
            return self._get_connected_person_view(person, user_person, request)
        
        # Get existing exclusive relations
        existing_parents = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['FATHER', 'MOTHER'],
            status__in=['confirmed', 'pending']
        ).values_list('relation__relation_code', flat=True)
        
        existing_spouses = PersonRelation.objects.filter(
            Q(from_person=person) | Q(to_person=person),
            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
            status__in=['confirmed', 'pending']
        ).exists()
        
        # Check if user can actually add relatives to this person
        user = request.user
        user_person = Person.objects.filter(linked_user=user).first()
        viewer_person = user_person
        
        # Determine permissions
        can_edit = False
        can_add_relatives = False
        is_readonly = False
        
        if user_person:
            # Check if same family
            if user_person.family_id == person.family_id:
                can_edit = True
                can_add_relatives = True
                is_readonly = False
            else:
                # Different family - check if connected
                is_connected = PersonRelation.objects.filter(
                    Q(from_person=person, to_person=user_person) |
                    Q(from_person=user_person, to_person=person),
                    status='confirmed'
                ).exists()
                
                if is_connected:
                    can_edit = False
                    can_add_relatives = False
                    is_readonly = True
                else:
                    # Not connected, different family, but person is placeholder
                    # Allow adding relatives to placeholder
                    can_edit = True
                    can_add_relatives = True
                    is_readonly = False
        
        # Base options for any person
        options = []
        
        # Only show add options if user can add relatives
        if can_add_relatives:
            # Add father option only if not already exists
            if 'FATHER' not in existing_parents:
                options.append({
                    'action': 'add_father',
                    'label': f"Add {person.full_name}'s Father",
                    'relation_code': 'FATHER',
                    'auto_gender': 'M',
                    'icon': '👴'
                })
            
            # Add mother option only if not already exists
            if 'MOTHER' not in existing_parents:
                options.append({
                    'action': 'add_mother',
                    'label': f"Add {person.full_name}'s Mother",
                    'relation_code': 'MOTHER',
                    'auto_gender': 'F',
                    'icon': '👵'
                })
            
            # Always allow children (can have multiple)
            options.extend([
                {
                    'action': 'add_son',
                    'label': f"Add {person.full_name}'s Son",
                    'relation_code': 'SON',
                    'auto_gender': 'M',
                    'icon': '👦'
                },
                {
                    'action': 'add_daughter',
                    'label': f"Add {person.full_name}'s Daughter",
                    'relation_code': 'DAUGHTER',
                    'auto_gender': 'F',
                    'icon': '👧'
                },
            ])
            
            # Always allow siblings (can have multiple)
            options.extend([
                {
                    'action': 'add_elder_brother',
                    'label': f"Add {person.full_name}'s Elder Brother",
                    'relation_code': 'ELDER_BROTHER',
                    'auto_gender': 'M',
                    'icon': '👨‍🦳',
                    'category': 'siblings'
                },
                {
                    'action': 'add_younger_brother',
                    'label': f"Add {person.full_name}'s Younger Brother",
                    'relation_code': 'YOUNGER_BROTHER',
                    'auto_gender': 'M',
                    'icon': '👨',
                    'category': 'siblings'
                },
                {
                    'action': 'add_elder_sister',
                    'label': f"Add {person.full_name}'s Elder Sister",
                    'relation_code': 'ELDER_SISTER',
                    'auto_gender': 'F',
                    'icon': '👩‍🦳',
                    'category': 'siblings'
                },
                {
                    'action': 'add_younger_sister',
                    'label': f"Add {person.full_name}'s Younger Sister",
                    'relation_code': 'YOUNGER_SISTER',
                    'auto_gender': 'F',
                    'icon': '👩',
                    'category': 'siblings'
                },
            ])
            
            # Add spouse option only if not already exists
            if not existing_spouses:
                if person.gender == 'M':
                    options.append({
                        'action': 'add_wife',
                        'label': f"Add {person.full_name}'s Wife",
                        'relation_code': 'WIFE',
                        'auto_gender': 'F',
                        'icon': '👰'
                    })
                elif person.gender == 'F':
                    options.append({
                        'action': 'add_husband',
                        'label': f"Add {person.full_name}'s Husband",
                        'relation_code': 'HUSBAND',
                        'auto_gender': 'M',
                        'icon': '🤵'
                    })
                else:
                    options.append({
                        'action': 'add_spouse',
                        'label': f"Add {person.full_name}'s Spouse",
                        'relation_code': 'SPOUSE',
                        'auto_gender': None,
                        'icon': '💑'
                    })
        
        # Always show skip/view options
        options.append({
            'action': 'view_tree',
            'label': 'View Family Tree',
            'icon': '🌳',
            'description': 'Browse family tree'
        })
        
        options.append({
            'action': 'skip',
            'label': 'Skip for now',
            'icon': '⏭️'
        })
        
        return Response({
        'status': 'placeholder_add_options',
        'person': {
            'id': person.id,
            'name': person.full_name,
            'gender': person.gender,
            'is_placeholder': person.linked_user is None,
            'has_father': 'FATHER' in existing_parents,
            'has_mother': 'MOTHER' in existing_parents,
            'has_spouse': existing_spouses
        },
        "existing_relations": existing_relations_data,  # ✅ Now shows from person's perspective
        'permissions': {
            'can_edit': can_edit,
            'can_add_relatives': can_add_relatives,
            'is_readonly': is_readonly
        },
        'options': options,
        'total_options': len(options)
    })
    
    def get_relation_to_me(self, me, other):
        """
        Very simple derived relation resolver.
        """
        # Direct relation
        rel = PersonRelation.objects.filter(
            Q(from_person=me, to_person=other) |
            Q(from_person=other, to_person=me),
            status='confirmed'
        ).select_related('relation').first()

        if rel:
            return rel.relation.relation_code

        # Sister's husband
        sister_rel = PersonRelation.objects.filter(
            from_person=me,
            relation__relation_code__in=["SISTER", "ELDER_SISTER", "YOUNGER_SISTER"],
            status='confirmed'
        ).values_list('to_person', flat=True)

        if PersonRelation.objects.filter(
            from_person__in=sister_rel,
            to_person=other,
            relation__relation_code="SPOUSE"
        ).exists():
            return "BROTHER_IN_LAW"

        # Sister's child
        if PersonRelation.objects.filter(
            from_person__in=sister_rel,
            to_person=other,
            relation__relation_code="CHILD"
        ).exists():
            return "NEPHEW"

        return "CONNECTED"
    
    def _get_connected_person_view(self, person, user_person, request):
        """Show read-only view of a connected person FROM PERSON'S POV."""
        # Get the relationship between viewer and this person
        relation = PersonRelation.objects.filter(
            Q(from_person=person, to_person=user_person) |
            Q(from_person=user_person, to_person=person),
            status='confirmed'
        ).select_related('relation').first()
        
        # ✅ CRITICAL: When viewing someone else's page, set 'me' to that person
        # This makes the serializer show relationships from THEIR perspective
        serializer_context = {
            'request': request,
            'me': person,           # ✅ The person being viewed (Banu)
            'viewing_person': person  # ✅ Same person
        }
        
        # Get existing exclusive relations FOR THE PERSON BEING VIEWED
        existing_parents = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=['FATHER', 'MOTHER'],
            status__in=['confirmed', 'pending']
        ).values_list('relation__relation_code', flat=True)
        
        existing_spouses = PersonRelation.objects.filter(
            Q(from_person=person) | Q(to_person=person),
            relation__relation_code__in=['HUSBAND', 'WIFE', 'SPOUSE'],
            status__in=['confirmed', 'pending']
        ).exists()
        
        # Get outgoing and incoming relations WITH CORRECT CONTEXT
        outgoing = PersonRelation.objects.filter(
            from_person=person,
            status__in=['confirmed', 'pending']
        ).select_related('to_person', 'relation')
        
        incoming = PersonRelation.objects.filter(
            to_person=person,
            status__in=['confirmed', 'pending']
        ).select_related('from_person', 'relation')
        
        # ✅ Serialize from PERSON'S perspective
        outgoing_data = PersonRelationSerializer(
            outgoing, 
            many=True, 
            context=serializer_context
        ).data
        
        incoming_data = PersonRelationSerializer(
            incoming, 
            many=True, 
            context=serializer_context
        ).data
        
        # Determine inverse relationship for connection info
        if relation:
            # Create context for this specific relation to show inverse
            relation_context = {
                'request': request,
                'me': person,  # Person being viewed
                'viewing_person': person
            }
            
            relation_serializer = PersonRelationSerializer(relation, context=relation_context)
            relation_data = relation_serializer.data
            
            # Get the inverse label
            inverse_label = relation_data.get('relation_label', {}).get('user_label')
        else:
            inverse_label = None
        
        # Build add options FROM PERSON'S POV (only if placeholder)
        add_options = []
        if person.linked_user is None:  # Only for placeholders
            # Add father option only if not already exists
            if 'FATHER' not in existing_parents:
                add_options.append({
                    'action': 'add_father',
                    'label': f"Add {person.full_name}'s Father",
                    'relation_code': 'FATHER',
                    'auto_gender': 'M',
                    'icon': '👴',
                    'description': 'Father of the person you are viewing'
                })
            
            # Add mother option only if not already exists
            if 'MOTHER' not in existing_parents:
                add_options.append({
                    'action': 'add_mother',
                    'label': f"Add {person.full_name}'s Mother",
                    'relation_code': 'MOTHER',
                    'auto_gender': 'F',
                    'icon': '👵',
                    'description': 'Mother of the person you are viewing'
                })
            
            # Add children options
            add_options.extend([
                {
                    'action': 'add_son',
                    'label': f"Add {person.full_name}'s Son",
                    'relation_code': 'SON',
                    'auto_gender': 'M',
                    'icon': '👦',
                    'description': f"Son of {person.full_name}"
                },
                {
                    'action': 'add_daughter',
                    'label': f"Add {person.full_name}'s Daughter",
                    'relation_code': 'DAUGHTER',
                    'auto_gender': 'F',
                    'icon': '👧',
                    'description': f"Daughter of {person.full_name}"
                },
            ])
            
            # Add sibling options
            add_options.extend([
                {
                    'action': 'add_elder_brother',
                    'label': f"Add {person.full_name}'s Elder Brother",
                    'relation_code': 'ELDER_BROTHER',
                    'auto_gender': 'M',
                    'icon': '👨‍🦳',
                    'description': f"Elder brother of {person.full_name}"
                },
                {
                    'action': 'add_younger_brother',
                    'label': f"Add {person.full_name}'s Younger Brother",
                    'relation_code': 'YOUNGER_BROTHER',
                    'auto_gender': 'M',
                    'icon': '👨',
                    'description': f"Younger brother of {person.full_name}"
                },
                {
                    'action': 'add_elder_sister',
                    'label': f"Add {person.full_name}'s Elder Sister",
                    'relation_code': 'ELDER_SISTER',
                    'auto_gender': 'F',
                    'icon': '👩‍🦳',
                    'description': f"Elder sister of {person.full_name}"
                },
                {
                    'action': 'add_younger_sister',
                    'label': f"Add {person.full_name}'s Younger Sister",
                    'relation_code': 'YOUNGER_SISTER',
                    'auto_gender': 'F',
                    'icon': '👩',
                    'description': f"Younger sister of {person.full_name}"
                },
            ])
            
            # Add spouse option only if not already exists
            if not existing_spouses:
                if person.gender == 'M':
                    add_options.append({
                        'action': 'add_wife',
                        'label': f"Add {person.full_name}'s Wife",
                        'relation_code': 'WIFE',
                        'auto_gender': 'F',
                        'icon': '👰',
                        'description': f"Wife of {person.full_name}"
                    })
                elif person.gender == 'F':
                    add_options.append({
                        'action': 'add_husband',
                        'label': f"Add {person.full_name}'s Husband",
                        'relation_code': 'HUSBAND',
                        'auto_gender': 'M',
                        'icon': '🤵',
                        'description': f"Husband of {person.full_name}"
                    })
                else:
                    add_options.append({
                        'action': 'add_spouse',
                        'label': f"Add {person.full_name}'s Spouse",
                        'relation_code': 'SPOUSE',
                        'auto_gender': None,
                        'icon': '💑',
                        'description': f"Spouse of {person.full_name}"
                    })
        
        # Get language from user profile for labels
        language = 'en'
        if request.user.is_authenticated and hasattr(request.user, 'profile'):
            language = getattr(request.user.profile, 'preferred_language', 'en')
        
        # Get family members WITH THEIR RELATION TO THE PERSON BEING VIEWED
        family_members = Person.objects.filter(
            family=person.family
        ).exclude(id=person.id)
        
        family_members_data = []
        for member in family_members:
            # Get relation from person being viewed to this family member
            relation_code = resolve_relation_to_me(
                person,         # ✅ Person being viewed (Banu)
                person,         # Same person (viewing themselves)
                member          # Family member
            )

            label = None
            if relation_code:
                label = RelationLabelService.get_relation_label(
                    relation_code=relation_code,
                    language=language,
                    religion=getattr(request.user.profile, 'religion', ''),
                    caste=getattr(request.user.profile, 'caste', '')
                )["label"]

            member_data = PersonSerializer(
                member,
                context={'request': request}
            ).data

            member_data["relation_to_viewed_person"] = {  # ✅ Changed key
                "code": relation_code,
                "label": label
            }

            family_members_data.append(member_data)
        
        # Determine permissions
        can_add_relatives = person.linked_user is None
        
        return Response({
            'status': 'connected_person_view',
            'view_type': 'connected_view',
            'permissions': {
                'can_edit': False,
                'can_add_relatives': can_add_relatives,
                'can_delete': False,
                'is_owner': False,
                'is_in_family': person.family_id == user_person.family_id,
                'is_connected': True,
                'is_readonly': not can_add_relatives
            },
            'connection_info': {
                'your_relation_to_them': relation.relation.relation_code if relation else None,
                'their_relation_to_you': inverse_label,  # What they call you (from their POV)
                'direction': 'from_user' if relation and relation.from_person == user_person else 'to_user',
                'relation_id': relation.id if relation else None
            },
            'person': PersonSerializer(person, context={'request': request}).data,
            'family_info': {
                'family_name': person.family.family_name if person.family else None,
                'family_id': person.family_id,
                'member_count': family_members.count() + 1,
                'viewer_family_match': person.family_id == user_person.family_id
            },
            'existing_relations': {
                'outgoing': outgoing_data,  # ✅ From person's POV
                'incoming': incoming_data,   # ✅ From person's POV
            },
            'family_members': family_members_data,
            'add_options': add_options,
            'available_actions': [
                {
                    'action': 'view_tree',
                    'label': f"View {person.full_name}'s Family Tree",
                    'icon': '🌳',
                    'description': f'Browse {person.full_name}\'s family tree'
                },
                {
                    'action': 'back_to_my_family',
                    'label': 'Back to My Family',
                    'icon': '↩️',
                    'description': 'Return to your family'
                },
                {
                    'action': 'view_connection_path',
                    'label': 'View Connection Path',
                    'icon': '🔄',
                    'description': 'See how you are connected'
                }
            ],
            'debug_info': {
                'viewer_person_id': user_person.id,
                'viewer_person_name': user_person.full_name,
                'viewed_person_id': person.id,
                'viewed_person_name': person.full_name,
                'serializer_context_me': person.id,  # Shows who 'me' is in serializer
                'is_viewing_own_person': user_person.id == person.id
            },
            'message': f'Viewing {person.full_name}\'s profile. {f"You are their {relation.relation.relation_code.lower()}" if relation else "Connected"}'
        })

    def _get_inverse_relation_code(self, relation_code, from_gender, to_gender):
        """Get inverse relation code."""
        INVERSE_MAP = {
            'FATHER': {'M': 'SON', 'F': 'DAUGHTER'},
            'MOTHER': {'M': 'SON', 'F': 'DAUGHTER'},
            'SON': {'M': 'FATHER', 'F': 'MOTHER'},
            'DAUGHTER': {'M': 'FATHER', 'F': 'MOTHER'},
            'HUSBAND': {'F': 'WIFE'},
            'WIFE': {'M': 'HUSBAND'},
            'ELDER_BROTHER': {'M': 'YOUNGER_BROTHER', 'F': 'YOUNGER_SISTER'},
            'YOUNGER_BROTHER': {'M': 'ELDER_BROTHER', 'F': 'ELDER_SISTER'},
            'BROTHER': {'M': 'BROTHER', 'F': 'SISTER'},
            'ELDER_SISTER': {'M': 'YOUNGER_BROTHER', 'F': 'YOUNGER_SISTER'},
            'YOUNGER_SISTER': {'M': 'ELDER_BROTHER', 'F': 'ELDER_SISTER'},
            'SISTER': {'M': 'BROTHER', 'F': 'SISTER'},
        }
        
        if relation_code in INVERSE_MAP:
            gender_map = INVERSE_MAP[relation_code]
            if to_gender in gender_map:
                return gender_map[to_gender]
        
        return f"INVERSE_{relation_code}"
    
    def _user_in_same_family(self, user, person):
        """Check if user is in same family as person."""
        user_person = Person.objects.filter(linked_user=user).first()
        return user_person and user_person.family_id == person.family_id
    
    def _get_or_create_current_person(self, user):
        from apps.families.models import Family

        person = Person.objects.filter(linked_user=user).first()
        
        # Sync with profile if person exists
        if person:
            person = self._sync_person_with_profile(person)
            return person
        
        # Create new person with profile gender
        family = Family.objects.filter(created_by=user).first()
        if not family:
            family = Family.objects.create(
                family_name=f"{user.mobile_number}'s Family",
                created_by=user
            )

        display_name = (
            user.profile.firstname.strip()
            if hasattr(user, 'profile') and user.profile.firstname
            else getattr(user, 'mobile_number', f"User_{user.id}")
        )

        # Get gender from user profile
        gender = 'M'  # default
        if hasattr(user, 'profile') and getattr(user.profile, 'gender', None):
            gender = user.profile.gender

        return Person.objects.create(
            linked_user=user,
            full_name=display_name,
            gender=gender,  # Use gender from profile
            family=family,
            is_alive=True
        )
    
    def _get_fixed_relation(self, relation_type, gender=None):
        """Get FixedRelation object based on relation type and gender."""
        RELATION_CODE_MAP = {
            'FATHER': 'FATHER',
            'MOTHER': 'MOTHER',
            'SON': 'SON',
            'DAUGHTER': 'DAUGHTER',
            'HUSBAND': 'HUSBAND',
            'WIFE': 'WIFE',
            'BROTHER': 'BROTHER',
            'SISTER': 'SISTER',
            'SPOUSE': 'HUSBAND' if gender == 'M' else 'WIFE',
            'PARTNER': 'PARTNER',
            'CHILD': 'SON' if gender == 'M' else 'DAUGHTER',
            'PARENT': 'FATHER' if gender == 'M' else 'MOTHER',
            'ELDER_BROTHER': 'ELDER_BROTHER',
            'YOUNGER_BROTHER': 'YOUNGER_BROTHER',
            'ELDER_SISTER': 'ELDER_SISTER',
            'YOUNGER_SISTER': 'YOUNGER_SISTER',
        }
        
        relation_type_upper = relation_type.upper() if relation_type else ''
        relation_code = RELATION_CODE_MAP.get(relation_type_upper, relation_type_upper)
        
        try:
            return FixedRelation.objects.get(relation_code=relation_code)
        except FixedRelation.DoesNotExist:
            if relation_type_upper in ['ELDER_BROTHER', 'YOUNGER_BROTHER', 'BROTHER']:
                return FixedRelation.objects.get(relation_code='BROTHER')
            elif relation_type_upper in ['ELDER_SISTER', 'YOUNGER_SISTER', 'SISTER']:
                return FixedRelation.objects.get(relation_code='SISTER')
            else:
                return FixedRelation.objects.first()

    def _get_existing_relations(self, person, viewer_person):
        """
        Get existing relations for a person, showing from THAT PERSON'S perspective.
        """
        relations = PersonRelation.objects.filter(
            Q(from_person=person) | Q(to_person=person),
            status='confirmed'
        ).select_related('relation', 'from_person', 'to_person')

        data = []
        for rel in relations:
            # Determine which person is the other (not the main person)
            if rel.from_person == person:
                other = rel.to_person
                direction = 'outgoing'
            else:
                other = rel.from_person
                direction = 'incoming'
            
            # ✅ CRITICAL: Create context from THE PERSON'S perspective
            # 'me' should be the person whose page we're viewing
            # 'viewing_person' is also the same person
            relation_context = {
                "request": self.request,
                "me": person,  # ✅ The person being viewed (vasanth_mother)
                "viewing_person": person  # ✅ Same person
            }
            
            # Serialize the relation from person's perspective
            serializer = PersonRelationSerializer(rel, context=relation_context)
            relation_data = serializer.data
            
            # Get the user_label (what the person calls the other person)
            user_label = relation_data.get('relation_label', {}).get('user_label')
            if not user_label:
                user_label = relation_data.get('relation_label', {}).get('label')
            
            # Get arrow_label from person's perspective
            arrow_label = relation_data.get('arrow_label')
            
            data.append({
                "person_id": other.id,
                "name": other.full_name,
                "direct_relation": rel.relation.relation_code,
                "relation_label": {
                    "label": relation_data.get('relation_label', {}).get('label', ''),
                    "source": relation_data.get('relation_label', {}).get('source', ''),
                    "user_label": user_label,
                    "arrow_label": arrow_label
                }
            })

        return data


class PersonRelationViewSet(viewsets.ModelViewSet):
    """ViewSet for PersonRelation operations."""
    serializer_class = PersonRelationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get relations for user's families."""
        user = self.request.user
        
        # Get families user belongs to
        family_ids = Person.objects.filter(
            linked_user=user
        ).values_list('family_id', flat=True)
        
        # Get persons in those families
        person_ids = Person.objects.filter(family_id__in=family_ids).values_list('id', flat=True)
        
        return PersonRelation.objects.filter(
            Q(from_person_id__in=person_ids) | Q(to_person_id__in=person_ids)
        ).select_related(
            'from_person', 'to_person', 'relation',
            'from_person__linked_user', 'to_person__linked_user'
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create relation with current user as creator."""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm a pending relation."""
        relation = self.get_object()
        
        # Check permissions
        if relation.to_person.linked_user != request.user:
            raise PermissionDenied("Only the target person can confirm this relation")
        
        if relation.status != 'pending':
            raise DjangoValidationError("Only pending relations can be confirmed")
        
        # Check for conflicts
        from apps.relations.services import ConflictDetectionService
        conflicts = ConflictDetectionService.detect_conflicts(
            relation.from_person_id,
            relation.to_person_id,
            relation.relation.relation_code
        )
        
        if conflicts:
            try:
                relation.mark_conflicted('; '.join(conflicts), request.user)
            except Exception as e:
                return Response({
                    'status': 'error',
                    'message': 'Failed to mark relation as conflicted',
                    'error': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response({
                            'status': 'conflicted',
                            'message': 'Relation has conflicts and cannot be confirmed',
                            'conflicts': conflicts
                        }, status=status.HTTP_400_BAD_REQUEST)
            
        # Confirm relation
        relation.confirm(request.user)
        
        # TODO: Create reciprocal relation if needed
        
        return Response({
            'status': 'confirmed',
            'message': 'Relation confirmed successfully'
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a pending relation."""
        relation = self.get_object()
        
        # Check permissions
        if relation.to_person.linked_user != request.user:
            raise PermissionDenied("Only the target person can reject this relation")
        
        if relation.status != 'pending':
            raise DjangoValidationError("Only pending relations can be rejected")
        
        relation.status = 'rejected'
        relation.resolved_by = request.user
        relation.resolved_at = timezone.now()
        relation.save()
        
        return Response({
            'status': 'rejected',
            'message': 'Relation rejected'
        })
    
    @action(detail=True, methods=['post'])
    def resolve_conflict(self, request, pk=None):
        """Resolve a conflicted relation."""
        relation = self.get_object()
        
        if relation.status != 'conflicted':
            raise DjangoValidationError("Only conflicted relations can be resolved")
        
        resolution = request.data.get('resolution')
        if resolution not in ['confirm', 'reject']:
            raise DjangoValidationError("Resolution must be 'confirm' or 'reject'")
        
        if resolution == 'confirm':
            # Admin or involved parties can confirm
            if not (request.user.is_staff or 
                    relation.from_person.linked_user == request.user or
                    relation.to_person.linked_user == request.user):
                raise PermissionDenied("You don't have permission to resolve this conflict")
            
            relation.confirm(request.user)
            message = 'Conflict resolved - relation confirmed'
        else:
            # Only admin or involved parties can reject
            if not (request.user.is_staff or
                    relation.from_person.linked_user == request.user or
                    relation.to_person.linked_user == request.user):
                raise PermissionDenied("You don't have permission to resolve this conflict")
            
            relation.status = 'rejected'
            relation.resolved_by = request.user
            relation.resolved_at = timezone.now()
            relation.save()
            message = 'Conflict resolved - relation rejected'
        
        return Response({
            'status': relation.status,
            'message': message
        })
    
    @action(detail=False, methods=['post'])
    def create_relation(self, request):
        """Create a new relation using simplified endpoint."""
        serializer = CreatePersonRelationSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            person_relation = serializer.save()
            response_serializer = PersonRelationSerializer(
                person_relation,
                context={'request': request}
            )
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TreeView(generics.GenericAPIView):
    """
    Family tree visualization API
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        print("HELLO 1",flush=True)
        serializer = TreeViewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        center_person_id = serializer.validated_data["center_person_id"]
        max_depth = serializer.validated_data.get("max_depth", 3)

        try:
            center_person = Person.objects.get(id=center_person_id)
        except Person.DoesNotExist:
            return Response(
                {"error": "Person not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ✅ SAFE ACCESS CHECK
        if center_person.linked_user != request.user:
            user_person = Person.objects.filter(linked_user=request.user).first()
            if not user_person or user_person.family_id != center_person.family_id:
                raise PermissionDenied("You don't have access to this family tree")
        
        print("POst")

        tree = self.get_tree_data(
            person=center_person,
            max_depth=max_depth,
            current_depth=0,
            visited=set()
        )

        return Response(tree)

    def get_tree_data(self, person, max_depth, current_depth, visited):
        """
        Recursive tree builder
        """
        if not person:
            return None

        if person.id in visited:
            return None

        if current_depth > max_depth:
            return None

        visited.add(person.id)
        print("person_data")
        person_data = {
            "id": person.id,
            "name": person.full_name,
            "gender": person.gender,
            "is_user": person.linked_user is not None,
            "depth": current_depth,
            "children": [],
            "parents": [],
            "spouses": [],
        }

        # --------------------
        # CHILDREN
        # (Children come from parent relations)
        # --------------------
        child_relations = PersonRelation.objects.filter(
            from_person=person,
            relation__relation_code__in=["FATHER", "MOTHER"],
            status="confirmed"
        ).select_related("to_person")

        for rel in child_relations:
            child_data = self.get_tree_data(
                rel.to_person,
                max_depth,
                current_depth + 1,
                visited
            )
            if child_data:
                person_data["children"].append({
                    "person": child_data,
                    "via": rel.relation.relation_code
                })

        # --------------------
        # PARENTS
        # --------------------
        parent_relations = PersonRelation.objects.filter(
            to_person=person,
            relation__relation_code__in=["FATHER", "MOTHER"],
            status="confirmed"
        ).select_related("from_person")
        print("parent is",parent_relations)

        for rel in parent_relations:
            parent_data = self.get_tree_data(
                rel.from_person,
                max_depth,
                current_depth + 1,
                visited
            )
            if parent_data:
                person_data["parents"].append({
                    "person": parent_data,
                    "via": rel.relation.relation_code
                })

        # --------------------
        # SPOUSES
        # --------------------
        spouse_relations = PersonRelation.objects.filter(
            Q(from_person=person) | Q(to_person=person),
            relation__relation_code__in=["HUSBAND", "WIFE"],
            status="confirmed"
        ).select_related("from_person", "to_person")

        for rel in spouse_relations:
            spouse = rel.to_person if rel.from_person == person else rel.from_person
            spouse_data = self.get_tree_data(
                spouse,
                max_depth,
                current_depth,
                visited
            )
            if spouse_data:
                person_data["spouses"].append({
                    "person": spouse_data,
                    "via": rel.relation.relation_code
                })

        return person_data


class PersonDetailView(RetrieveAPIView):
    """View for getting person details with generation and member counts."""
    serializer_class = PersonSerializer
    queryset = Person.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        
        # Add 'me' (current user's person) to context for generation calculation
        me = Person.objects.filter(linked_user=self.request.user).first()
        if me:
            context['me'] = me
            
        return context
    
    def get_queryset(self):
        """Limit queryset to persons user has access to."""
        user = self.request.user
        user_person = Person.objects.filter(linked_user=user).first()
        
        if not user_person:
            return Person.objects.none()
        
        # Get persons in user's family OR connected to user
        family_person_ids = Person.objects.filter(
            family=user_person.family
        ).values_list('id', flat=True)
        
        # Get connected persons from other families
        connected_relations = PersonRelation.objects.filter(
            Q(from_person=user_person) | Q(to_person=user_person),
            status='confirmed'
        )
        
        connected_person_ids = set()
        for rel in connected_relations:
            if rel.from_person != user_person:
                connected_person_ids.add(rel.from_person.id)
            if rel.to_person != user_person:
                connected_person_ids.add(rel.to_person.id)
        
        all_person_ids = set(family_person_ids) | connected_person_ids
        
        return Person.objects.filter(id__in=all_person_ids).select_related(
            'linked_user', 'linked_user__profile', 'family'
        )