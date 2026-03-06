"""
Core service for relation label resolution.
Implements the 5-level fallback system including profile overrides.
"""
from typing import Optional, Dict, Any, List, Tuple
from django.db.models import Q
from django.core.cache import cache
import logging
from functools import lru_cache
from django.core.exceptions import ValidationError
from datetime import datetime

from .models import (
    FixedRelation,
    RelationFamily,
    RelationCaste,
    RelationLanguageReligion,
    RelationProfileOverride
)

# Configure logger
logger = logging.getLogger(__name__)

class RelationLabelService:
    """
    Service for resolving relationship labels using 5-level fallback system.
    
    Resolution order (STRICT from most to least specific):
    1. RelationProfileOverride (most specific - matches ALL provided fields)
    2. RelationFamily
    3. RelationCaste
    4. RelationLanguageReligion
    5. FixedRelation default (least specific)
    """
    
    # Cache timeout in seconds (1 hour)
    CACHE_TIMEOUT = 3600
    
    @classmethod
    def get_relation_label(
        cls,
        relation_code: str,
        language: str,
        religion: str = None,
        caste: str = None,
        family_name: Optional[str] = None,
        native: Optional[str] = None,
        present_city: Optional[str] = None,
        taluk: Optional[str] = None,
        district: Optional[str] = None,
        state: Optional[str] = None,
        nationality: Optional[str] = None,
        gender_context: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get relation label using 5-level fallback system including profile fields.
        
        Args:
            relation_code: Fixed relation code (e.g., 'FATHER')
            language: Preferred language (e.g., 'ta', 'en')
            religion: User's religion
            caste: User's caste
            family_name: Family name for level 2 override
            native: Native place
            present_city: Present city
            taluk: Taluk
            district: District
            state: State
            nationality: Nationality
            gender_context: Gender context for language-specific forms
            use_cache: Whether to use cache for lookups
        
        Returns:
            Dictionary with label and metadata
        """
        # Input validation
        if not relation_code:
            logger.error("Empty relation code provided")
            return {
                'label': '',
                'level': 'error',
                'relation_code': relation_code,
                'error': 'Invalid relation code'
            }
        
        # Set defaults for None values
        language = language or 'en'
        religion = religion or ''
        caste = caste or ''
        family_name = family_name or ''
        native = native or ''
        present_city = present_city or ''
        taluk = taluk or ''
        district = district or ''
        state = state or ''
        nationality = nationality or ''
        
        # Generate cache key including all fields
        cache_key = f"relation_label:v2:{relation_code}:{language}:{religion}:{caste}:{family_name}:{native}:{present_city}:{taluk}:{district}:{state}:{nationality}"
        
        if use_cache:
            cached_result = cache.get(cache_key)
            if cached_result:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result
        
        try:
            # Get relation with error handling
            try:
                relation = FixedRelation.objects.get(relation_code=relation_code, is_active=True)
            except FixedRelation.DoesNotExist:
                logger.warning(f"Relation code not found: {relation_code}")
                return {
                    'label': relation_code,
                    'level': 'not_found',
                    'relation_code': relation_code,
                    'error': 'Relation code does not exist'
                }
            except Exception as e:
                logger.error(f"Database error fetching relation {relation_code}: {str(e)}")
                return {
                    'label': relation_code,
                    'level': 'error',
                    'relation_code': relation_code,
                    'error': f'Database error: {str(e)}'
                }
            
            # LEVEL 1: Profile override (most specific - matches all provided fields)
            try:
                profile_override = cls._find_matching_profile_override(
                    relation=relation,
                    language=language,
                    religion=religion,
                    caste=caste,
                    family=family_name,
                    native=native,
                    present_city=present_city,
                    taluk=taluk,
                    district=district,
                    state=state,
                    nationality=nationality
                )
                
                if profile_override:
                    result = {
                        'label': profile_override.label,
                        'level': 'profile_override',
                        'relation_code': relation_code,
                        'source': 'profile_override',
                        'metadata': {
                            'language': language,
                            'religion': religion,
                            'caste': caste,
                            'family': family_name,
                            'native': native,
                            'present_city': present_city,
                            'taluk': taluk,
                            'district': district,
                            'state': state,
                            'nationality': nationality,
                            'specificity_score': profile_override.get_specificity_score()
                        }
                    }
                    if use_cache:
                        cache.set(cache_key, result, cls.CACHE_TIMEOUT)
                    return result
            except Exception as e:
                logger.error(f"Error checking profile override for {relation_code}: {str(e)}")
            
            # LEVEL 2: Family-specific override
            if family_name and caste and religion:
                try:
                    family_label = RelationFamily.objects.select_related('relation').get(
                        relation=relation,
                        language=language,
                        religion=religion,
                        caste=caste,
                        family=family_name
                    )
                    result = {
                        'label': family_label.label,
                        'level': 'family',
                        'relation_code': relation_code,
                        'source': 'family_override',
                        'metadata': {
                            'family': family_name,
                            'language': language,
                            'religion': religion,
                            'caste': caste
                        }
                    }
                    if use_cache:
                        cache.set(cache_key, result, cls.CACHE_TIMEOUT)
                    return result
                except RelationFamily.DoesNotExist:
                    logger.debug(f"No family override found for {relation_code} with family {family_name}")
                except Exception as e:
                    logger.error(f"Error fetching family override for {relation_code}: {str(e)}")
            
            # LEVEL 3: Caste-specific label
            if caste and religion:
                try:
                    caste_label = RelationCaste.objects.select_related('relation').get(
                        relation=relation,
                        language=language,
                        religion=religion,
                        caste=caste
                    )
                    result = {
                        'label': caste_label.label,
                        'level': 'caste',
                        'relation_code': relation_code,
                        'source': 'caste_override',
                        'metadata': {
                            'language': language,
                            'religion': religion,
                            'caste': caste
                        }
                    }
                    if use_cache:
                        cache.set(cache_key, result, cls.CACHE_TIMEOUT)
                    return result
                except RelationCaste.DoesNotExist:
                    logger.debug(f"No caste override found for {relation_code} with caste {caste}")
                except Exception as e:
                    logger.error(f"Error fetching caste override for {relation_code}: {str(e)}")
            
            # LEVEL 4: Language + Religion label
            if religion:
                try:
                    lang_religion_label = RelationLanguageReligion.objects.select_related('relation').get(
                        relation=relation,
                        language=language,
                        religion=religion
                    )
                    result = {
                        'label': lang_religion_label.label,
                        'level': 'language_religion',
                        'relation_code': relation_code,
                        'source': 'religion_override',
                        'metadata': {
                            'language': language,
                            'religion': religion
                        }
                    }
                    if use_cache:
                        cache.set(cache_key, result, cls.CACHE_TIMEOUT)
                    return result
                except RelationLanguageReligion.DoesNotExist:
                    logger.debug(f"No language-religion override found for {relation_code} with religion {religion}")
                except Exception as e:
                    logger.error(f"Error fetching language-religion override for {relation_code}: {str(e)}")
            
            # LEVEL 5: Fixed relation default
            if language and language.lower() == 'ta':
                label = relation.default_tamil
            else:
                label = relation.default_english
            
            result = {
                'label': label,
                'level': 'default',
                'relation_code': relation_code,
                'source': 'system_default',
                'metadata': {
                    'language': language,
                    'default_type': 'tamil' if language and language.lower() == 'ta' else 'english'
                }
            }
            
            if use_cache:
                cache.set(cache_key, result, cls.CACHE_TIMEOUT)
            
            return result
            
        except Exception as e:
            logger.error(f"Unexpected error in get_relation_label for {relation_code}: {str(e)}", exc_info=True)
            return {
                'label': relation.default_english if 'relation' in locals() else relation_code,
                'level': 'error_fallback',
                'relation_code': relation_code,
                'error': f'Unexpected error: {str(e)}'
            }
    
    @classmethod
    def _find_matching_profile_override(cls, relation, **kwargs):
        """
        Find the most specific profile override matching all provided fields.
        
        A field matches if:
        - The override has the exact same value, OR
        - The override has NULL/empty for that field (meaning it doesn't care)
        """
        try:
            # Start with base relation filter
            query = Q(relation=relation)
            
            # Define all possible fields
            fields = ['language', 'religion', 'caste', 'family', 'native', 
                    'present_city', 'taluk', 'district', 'state', 'nationality']
            
            # For each field that has a value in kwargs, build the query
            for field in fields:
                value = kwargs.get(field)
                
                # If value is provided (not None and not empty string)
                if value is not None and value != '':
                    # Override must either:
                    # 1. Match exactly, OR
                    # 2. Have NULL/empty (meaning it doesn't care about this field)
                    query &= (
                        Q(**{field: value}) | 
                        Q(**{field: ''}) | 
                        Q(**{field: None})
                    )
                # If value is not provided or empty, don't filter on this field
                # This allows overrides with ANY value in this field to match
            
            # Execute query
            overrides = RelationProfileOverride.objects.filter(query)
            
            if not overrides.exists():
                logger.debug(f"No profile overrides found for {relation.relation_code}")
                return None
            
            # Log all found overrides (using logger, not print)
            logger.debug(f"Found {overrides.count()} potential overrides:")
            for o in overrides:
                fields_present = []
                if o.language: fields_present.append('language')
                if o.religion: fields_present.append('religion')
                if o.caste: fields_present.append('caste')
                if o.family: fields_present.append('family')
                if o.native: fields_present.append('native')
                if o.present_city: fields_present.append('present_city')
                if o.taluk: fields_present.append('taluk')
                if o.district: fields_present.append('district')
                if o.state: fields_present.append('state')
                if o.nationality: fields_present.append('nationality')
                
                logger.debug(f"  Override {o.id}: fields={fields_present}, label={o.label}")
            
            # Return the most specific (most fields filled)
            most_specific = max(overrides, key=lambda o: sum([
                1 for f in fields if getattr(o, f, None) not in [None, '']
            ]))
            
            logger.debug(f"Selected override {most_specific.id}")
            return most_specific
            
        except Exception as e:
            logger.error(f"Error in _find_matching_profile_override: {str(e)}", exc_info=True)
            return None
    
    @classmethod
    def get_label_from_user_profile(
        cls,
        relation_code: str,
        user,
        language: str = 'ta'
    ) -> Dict[str, Any]:
        """
        Convenience method to get label using a User object with profile.
        """
        try:
            if not hasattr(user, 'profile'):
                return cls.get_relation_label(relation_code, language=language)
            
            profile = user.profile
            
            return cls.get_relation_label(
                relation_code=relation_code,
                language=language,
                religion=getattr(profile, 'religion', None),
                caste=getattr(profile, 'caste', None),
                family_name=getattr(profile, 'familyname1', None),
                native=getattr(profile, 'native', None),
                present_city=getattr(profile, 'present_city', None),
                taluk=getattr(profile, 'taluk', None),
                district=getattr(profile, 'district', None),
                state=getattr(profile, 'state', None),
                nationality=getattr(profile, 'nationality', None)
            )
            
        except Exception as e:
            logger.error(f"Error getting label from user profile: {str(e)}")
            return cls.get_relation_label(relation_code, language=language)
    
    @classmethod
    def get_all_labels_for_context(
        cls,
        language: str,
        religion: str = None,
        caste: str = None,
        family_name: Optional[str] = None,
        native: Optional[str] = None,
        present_city: Optional[str] = None,
        taluk: Optional[str] = None,
        district: Optional[str] = None,
        state: Optional[str] = None,
        nationality: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, str]:
        """
        Get all relation labels for a given context.
        Useful for caching or pre-loading.
        """
        cache_key = f"all_labels:v2:{language}:{religion}:{caste}:{family_name}:{native}:{present_city}:{taluk}:{district}:{state}:{nationality}"
        
        if use_cache:
            cached_labels = cache.get(cache_key)
            if cached_labels:
                logger.debug(f"Cache hit for all labels: {cache_key}")
                return cached_labels
        
        try:
            labels = {}
            errors = []
            
            # Get all active fixed relations
            try:
                relations = FixedRelation.objects.filter(is_active=True).only(
                    'relation_code', 'default_english', 'default_tamil'
                )
            except Exception as e:
                logger.error(f"Error fetching fixed relations: {str(e)}")
                return {}
            
            total_relations = relations.count()
            logger.info(f"Fetching labels for {total_relations} relations")
            
            for idx, relation in enumerate(relations, 1):
                try:
                    result = cls.get_relation_label(
                        relation_code=relation.relation_code,
                        language=language,
                        religion=religion,
                        caste=caste,
                        family_name=family_name,
                        native=native,
                        present_city=present_city,
                        taluk=taluk,
                        district=district,
                        state=state,
                        nationality=nationality,
                        use_cache=use_cache
                    )
                    labels[relation.relation_code] = result['label']
                    
                    # Log progress for large batches
                    if idx % 100 == 0:
                        logger.debug(f"Processed {idx}/{total_relations} relations")
                        
                except Exception as e:
                    error_msg = f"Error processing relation {relation.relation_code}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    labels[relation.relation_code] = relation.default_english
            
            result = {
                'labels': labels,
                'metadata': {
                    'total': total_relations,
                    'successful': len(labels) - len(errors),
                    'failed': len(errors),
                    'errors': errors[:10]  # Limit errors in response
                }
            }
            
            if use_cache and len(errors) == 0:
                cache.set(cache_key, result, cls.CACHE_TIMEOUT)
            
            return result['labels']
            
        except Exception as e:
            logger.error(f"Unexpected error in get_all_labels_for_context: {str(e)}", exc_info=True)
            return {}
    
    @classmethod
    def validate_gender_compatibility(
        cls,
        relation_code: str,
        from_gender: str,
        to_gender: str
    ) -> bool:
        """
        Validate if genders are compatible for a relation.
        
        Args:
            relation_code: The relation code
            from_gender: Gender of 'from' person
            to_gender: Gender of 'to' person
        
        Returns:
            Boolean indicating if genders are compatible
        """
        # Input validation
        if not all([relation_code, from_gender, to_gender]):
            logger.warning(f"Invalid input for gender validation: relation={relation_code}, from={from_gender}, to={to_gender}")
            return False
        
        if from_gender not in ['M', 'F', 'O'] or to_gender not in ['M', 'F', 'O']:
            logger.warning(f"Invalid gender values: from={from_gender}, to={to_gender}")
            return False
        
        try:
            # Validate relation exists
            try:
                relation = FixedRelation.objects.get(relation_code=relation_code)
            except FixedRelation.DoesNotExist:
                logger.warning(f"Relation code not found for gender validation: {relation_code}")
                return False
            
            # Gender rules dictionary
            gender_rules = {
                'FATHER': {'from_gender': 'M'},   # father's gender matters
                'MOTHER': {'from_gender': 'F'},   # mother's gender matters
                'SON': {},
                'DAUGHTER': {},
                'SISTER': {'from_gender': 'F'},
                'BROTHER': {'from_gender': 'M'},
                'HUSBAND': {'from_gender': 'M', 'to_gender': 'F'},
                'WIFE': {'from_gender': 'F', 'to_gender': 'M'},
                'YOUNGER_BROTHER': {'from_gender': 'M'},
                'ELDER_BROTHER': {'from_gender': 'M'},
                'YOUNGER_SISTER': {'from_gender': 'F'},
                'ELDER_SISTER': {'from_gender': 'F'},
                'FATHER_ELDER_BROTHER': {'from_gender': 'M'},
                'FATHER_YOUNGER_BROTHER': {'from_gender': 'M'},
                'FATHER_SISTER': {'from_gender': 'F'},
                'MOTHER_BROTHER': {'from_gender': 'M'},
                'MOTHER_ELDER_SISTER': {'from_gender': 'F'},
                'MOTHER_YOUNGER_SISTER': {'from_gender': 'F'},
            }
            
            # If no specific rules, return True
            if relation_code not in gender_rules:
                logger.debug(f"No gender rules for {relation_code}, allowing")
                return True
            
            rules = gender_rules[relation_code]
            
            # Check from_gender rule
            if 'from_gender' in rules and rules['from_gender'] != from_gender:
                logger.debug(f"From gender mismatch for {relation_code}: expected {rules['from_gender']}, got {from_gender}")
                return False
            
            # Check to_gender rule
            if 'to_gender' in rules and rules['to_gender'] != to_gender:
                logger.debug(f"To gender mismatch for {relation_code}: expected {rules['to_gender']}, got {to_gender}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error in gender validation for {relation_code}: {str(e)}", exc_info=True)
            return False


class ConflictDetectionService:
    """Service for detecting relation conflicts."""
    
    @classmethod
    def detect_conflicts(
        cls,
        from_person_id: int,
        to_person_id: int,
        relation_code: str,
        check_reciprocal: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Detect conflicts for a proposed relation.
        
        Returns list of conflict messages with details.
        """
        conflicts = []
        
        # Input validation
        if not all([from_person_id, to_person_id, relation_code]):
            logger.warning(f"Invalid input for conflict detection: from={from_person_id}, to={to_person_id}, relation={relation_code}")
            return [{'type': 'invalid_input', 'message': 'Invalid input parameters'}]
        
        if from_person_id == to_person_id:
            return [{'type': 'self_relation', 'message': 'Cannot create relation with self'}]
        
        try:
            # Import here to avoid circular imports
            from apps.genealogy.models import PersonRelation
            
            # Get relation instance with error handling
            try:
                fixed_relation = FixedRelation.objects.get(relation_code=relation_code)
            except FixedRelation.DoesNotExist:
                logger.error(f"Relation code not found in conflict detection: {relation_code}")
                return [{'type': 'invalid_relation', 'message': f'Relation {relation_code} does not exist'}]
            
            # Check existing relations
            try:
                existing_relations = PersonRelation.objects.filter(
                    from_person_id=from_person_id,
                    to_person_id=to_person_id
                ).exclude(status='conflicted')
                
                # Check for duplicate relation
                if existing_relations.filter(relation__relation_code=relation_code).exists():
                    conflicts.append({
                        'type': 'duplicate',
                        'message': f'Relation {relation_code} already exists between these persons',
                        'severity': 'error'
                    })
            except Exception as e:
                logger.error(f"Error checking existing relations: {str(e)}")
                conflicts.append({
                    'type': 'database_error',
                    'message': f'Error checking existing relations: {str(e)}',
                    'severity': 'warning'
                })
            
            # Check biological limits for parent-child relationships
            if relation_code in ['FATHER', 'MOTHER']:
                try:
                    parent_count = PersonRelation.objects.filter(
                        from_person_id=from_person_id,
                        relation__relation_code=relation_code,
                        status='confirmed'
                    ).count()
                    
                    # Get max instances from FixedRelation
                    if fixed_relation.max_instances and fixed_relation.max_instances > 0:
                        if parent_count >= fixed_relation.max_instances:
                            conflicts.append({
                                'type': 'biological_limit',
                                'message': f'Cannot have more than {fixed_relation.max_instances} {relation_code}(s)',
                                'severity': 'error',
                                'current_count': parent_count,
                                'max_allowed': fixed_relation.max_instances
                            })
                except Exception as e:
                    logger.error(f"Error checking biological limits: {str(e)}")
                    conflicts.append({
                        'type': 'database_error',
                        'message': f'Error checking biological limits: {str(e)}',
                        'severity': 'warning'
                    })
            
            # Check reciprocal mismatch
            if check_reciprocal:
                try:
                    existing_reverse = PersonRelation.objects.filter(
                        from_person_id=to_person_id,
                        to_person_id=from_person_id,
                        status='confirmed'
                    ).select_related('relation')
                    
                    for reverse_rel in existing_reverse:
                        # Check if reverse relation is compatible
                        if not cls._is_reciprocal_compatible(relation_code, reverse_rel.relation.relation_code):
                            conflicts.append({
                                'type': 'reciprocal_mismatch',
                                'message': f'Incompatible with existing reverse relation: {reverse_rel.relation.relation_code}',
                                'severity': 'warning',
                                'existing_relation': reverse_rel.relation.relation_code
                            })
                except Exception as e:
                    logger.error(f"Error checking reciprocal relations: {str(e)}")
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Unexpected error in conflict detection: {str(e)}", exc_info=True)
            return [{
                'type': 'unexpected_error',
                'message': f'Unexpected error: {str(e)}',
                'severity': 'error'
            }]
    
    @classmethod
    def _is_reciprocal_compatible(cls, relation_code: str, reverse_code: str) -> bool:
        """Check if two relations are compatible as reciprocals."""
        reciprocal_pairs = {
            'FATHER': ['SON', 'DAUGHTER'],
            'MOTHER': ['SON', 'DAUGHTER'],
            'SON': ['FATHER', 'MOTHER'],
            'DAUGHTER': ['FATHER', 'MOTHER'],
            'HUSBAND': ['WIFE'],
            'WIFE': ['HUSBAND'],
            'ELDER_BROTHER': ['YOUNGER_BROTHER', 'YOUNGER_SISTER'],
            'ELDER_SISTER': ['YOUNGER_BROTHER', 'YOUNGER_SISTER'],
            'YOUNGER_BROTHER': ['ELDER_BROTHER', 'ELDER_SISTER'],
            'YOUNGER_SISTER': ['ELDER_BROTHER', 'ELDER_SISTER'],
        }
        
        return reverse_code in reciprocal_pairs.get(relation_code, [])


# 1️⃣ Relation composition table (ENHANCED with more combinations)
RELATION_COMPOSITION = {
    # Grandparents
    ("FATHER", "FATHER"): "GRANDFATHER",
    ("FATHER", "MOTHER"): "GRANDMOTHER",
    ("MOTHER", "FATHER"): "GRANDFATHER",
    ("MOTHER", "MOTHER"): "GRANDMOTHER",
    
    # Parent's siblings
    ("FATHER", "BROTHER"): "FATHER_BROTHER",
    ("FATHER", "ELDER_BROTHER"): "FATHER_ELDER_BROTHER",
    ("FATHER", "YOUNGER_BROTHER"): "FATHER_YOUNGER_BROTHER",
    ("FATHER", "SISTER"): "FATHER_SISTER",
    
    ("MOTHER", "BROTHER"): "MOTHER_BROTHER",
    ("MOTHER", "SISTER"): "MOTHER_SISTER",
    ("MOTHER", "ELDER_SISTER"): "MOTHER_ELDER_SISTER",
    ("MOTHER", "YOUNGER_SISTER"): "MOTHER_YOUNGER_SISTER",
    
    # Parent's spouses (step-parents)
    ("FATHER", "WIFE"): "STEP_MOTHER",
    ("MOTHER", "HUSBAND"): "STEP_FATHER",
    
    # Sibling's spouses
    ("ELDER_BROTHER", "WIFE"): "SISTER_IN_LAW",
    ("YOUNGER_BROTHER", "WIFE"): "SISTER_IN_LAW",
    ("ELDER_SISTER", "HUSBAND"): "BROTHER_IN_LAW",
    ("YOUNGER_SISTER", "HUSBAND"): "BROTHER_IN_LAW",
    
    # Children's spouses
    ("SON", "WIFE"): "DAUGHTER_IN_LAW",
    ("DAUGHTER", "HUSBAND"): "SON_IN_LAW",
    
    # Spouse's relatives
    ("HUSBAND", "FATHER"): "FATHER_IN_LAW",
    ("HUSBAND", "MOTHER"): "MOTHER_IN_LAW",
    ("HUSBAND", "BROTHER"): "BROTHER_IN_LAW",
    ("HUSBAND", "SISTER"): "SISTER_IN_LAW",
    
    ("WIFE", "FATHER"): "FATHER_IN_LAW",
    ("WIFE", "MOTHER"): "MOTHER_IN_LAW",
    ("WIFE", "BROTHER"): "BROTHER_IN_LAW",
    ("WIFE", "SISTER"): "SISTER_IN_LAW",
    
    # Nephews/Nieces
    ("ELDER_BROTHER", "SON"): "NEPHEW",
    ("ELDER_BROTHER", "DAUGHTER"): "NIECE",
    ("YOUNGER_BROTHER", "SON"): "NEPHEW",
    ("YOUNGER_BROTHER", "DAUGHTER"): "NIECE",
    ("ELDER_SISTER", "SON"): "NEPHEW",
    ("ELDER_SISTER", "DAUGHTER"): "NIECE",
    ("YOUNGER_SISTER", "SON"): "NEPHEW",
    ("YOUNGER_SISTER", "DAUGHTER"): "NIECE",
    
    # Grandchildren
    ("SON", "SON"): "GRANDSON",
    ("SON", "DAUGHTER"): "GRANDDAUGHTER",
    ("DAUGHTER", "SON"): "GRANDSON",
    ("DAUGHTER", "DAUGHTER"): "GRANDDAUGHTER",
    
    # Cousins (Uncle/Aunt's children)
    ("FATHER_BROTHER", "SON"): "COUSIN_MALE",
    ("FATHER_BROTHER", "DAUGHTER"): "COUSIN_FEMALE",
    ("FATHER_SISTER", "SON"): "COUSIN_MALE",
    ("FATHER_SISTER", "DAUGHTER"): "COUSIN_FEMALE",
    ("MOTHER_BROTHER", "SON"): "COUSIN_MALE",
    ("MOTHER_BROTHER", "DAUGHTER"): "COUSIN_FEMALE",
    ("MOTHER_SISTER", "SON"): "COUSIN_MALE",
    ("MOTHER_SISTER", "DAUGHTER"): "COUSIN_FEMALE",
    
    # Step-siblings
    ("STEP_FATHER", "SON"): "STEP_BROTHER",
    ("STEP_FATHER", "DAUGHTER"): "STEP_SISTER",
    ("STEP_MOTHER", "SON"): "STEP_BROTHER",
    ("STEP_MOTHER", "DAUGHTER"): "STEP_SISTER",
    
    # Multi-level compositions
    ("GRANDFATHER", "SON"): "UNCLE",
    ("GRANDFATHER", "DAUGHTER"): "AUNT",
    ("GRANDMOTHER", "SON"): "UNCLE",
    ("GRANDMOTHER", "DAUGHTER"): "AUNT",
}


# 2️⃣ Direct relation finder with error handling
def get_direct_relation(from_person, to_person):
    """
    Returns relation_code ONLY if explicitly stored
    in this direction with error handling.
    """
    try:
        # Validate inputs
        if not from_person or not to_person:
            logger.warning("Invalid person objects in get_direct_relation")
            return None
        
        if from_person.id == to_person.id:
            return "SELF"
        
        # Import here to avoid circular imports
        from apps.genealogy.models import PersonRelation
        
        relation = PersonRelation.objects.filter(
            from_person=from_person,
            to_person=to_person,
            status__in=["confirmed", "pending"]
        ).select_related("relation").first()
        
        if not relation:
            return None
        
        return relation.relation.relation_code
        
    except Exception as e:
        logger.error(f"Error in get_direct_relation: {str(e)}", exc_info=True)
        return None


# 3️⃣ Final resolver with comprehensive error handling (THIS IS THE BRAIN)
def resolve_relation_to_me(me, root_person, member):
    """
    me           = logged-in user's Person
    root_person  = person you clicked (sister)
    member       = one member in her family
    
    Returns resolved relation code with error handling.
    """
    try:
        # Validate inputs
        if not all([me, root_person, member]):
            logger.error(f"Invalid input to resolve_relation_to_me: me={me}, root={root_person}, member={member}")
            return "ERROR"
        
        # If same person
        if member.id == me.id:
            return "SELF"
        
        # Try direct relation
        explicit = get_direct_relation(me, member)
        if explicit:
            return explicit
        
        # My relation to root person (SISTER)
        base_relation = get_direct_relation(me, root_person)
        
        # Root person itself
        if member.id == root_person.id:
            return base_relation or "CONNECTED"
        
        # Root person's relation to member (SON / HUSBAND)
        member_relation = get_direct_relation(root_person, member)
        
        if not base_relation or not member_relation:
            logger.debug(f"Missing relations: base={base_relation}, member={member_relation}")
            return "CONNECTED"
        
        # Check composition table
        composed_relation = RELATION_COMPOSITION.get(
            (base_relation, member_relation),
            "CONNECTED"
        )
        
        logger.debug(f"Resolved relation: base={base_relation}, member={member_relation} -> {composed_relation}")
        
        return composed_relation
        
    except Exception as e:
        logger.error(f"Unexpected error in resolve_relation_to_me: {str(e)}", exc_info=True)
        return "ERROR"


class AshramamLabelService:
    """Service for Ashramam-specific labels with comprehensive error handling."""
    
    LABELS = {
        "THATHA": {"ta": "தாத்தா", "en": "Grandfather / Elder Man"},
        "PAATI": {"ta": "பாட்டி", "en": "Grandmother / Elder Woman"},

        "PERIYAPPA": {"ta": "பெரியப்பா", "en": "Father’s Elder Brother"},
        "PERIYAMMA": {"ta": "பெரியம்மா", "en": "Father’s Elder Brother’s Wife"},

        "CHITHAPPA": {"ta": "சித்தப்பா", "en": "Father’s Younger Brother"},
        "CHITHI": {"ta": "சித்தி", "en": "Father’s Younger Brother’s Wife"},

        "MAMA": {"ta": "மாமா", "en": "Maternal Uncle"},
        "ATHAI": {"ta": "அத்தை", "en": "Paternal Aunt"},
        "ATHAN": {"ta": "அத்தான்", "en": "Aunt’s Husband / Elder Brother-in-law"},
        "ANNI": {"ta": "அண்ணி", "en": "Elder Brother’s Wife"},

        "KOLUNTHANAR": {"ta": "கொழுந்தனார்", "en": "Wife’s Younger Brother"},
        "KOLUNTHIYAZH": {"ta": "கொழுந்தியாள்", "en": "Wife’s Younger Sister"},

        "MARUMAGAN": {"ta": "மருமகன்", "en": "Son-in-law"},
        "MARUMAGAL": {"ta": "மருமகள்", "en": "Daughter-in-law"},

        "PERAN": {"ta": "பேரன்", "en": "Grandson"},
        "PETTHI": {"ta": "பேத்தி", "en": "Granddaughter"},

        "MAITHUNAR": {"ta": "மைத்துனர்", "en": "Brother-in-law"},

        "MAGAN": {"ta": "மகன்", "en": "Son"},
        "MAGHAZH": {"ta": "மகள்", "en": "Daughter"},
        
        "ANNA": {"ta": "அண்ணன்", "en": "Elder Brother"},
        "AKKA": {"ta": "அக்கா", "en": "Elder Sister"},
        "THAMBI": {"ta": "தம்பி", "en": "Younger Brother"},
        "THANGAI": {"ta": "தங்கை", "en": "Younger Sister"},
        
        # Additional Tamil relation codes
        "FATHER_ELDER_BROTHER": {"ta": "பெரியப்பா", "en": "Father's Elder Brother"},
        "FATHER_YOUNGER_BROTHER": {"ta": "சித்தப்பா", "en": "Father's Younger Brother"},
        "FATHER_SISTER": {"ta": "அத்தை", "en": "Father's Sister"},
        "MOTHER_BROTHER": {"ta": "மாமா", "en": "Mother's Brother"},
        "MOTHER_ELDER_SISTER": {"ta": "பெரியம்மா", "en": "Mother's Elder Sister"},
        "MOTHER_YOUNGER_SISTER": {"ta": "சித்தி", "en": "Mother's Younger Sister"},
        "FATHER_IN_LAW": {"ta": "மாமனார்", "en": "Father-in-law"},
        "MOTHER_IN_LAW": {"ta": "மாமியார்", "en": "Mother-in-law"},
        "BROTHER_IN_LAW": {"ta": "அத்தான் / மைத்துனர்", "en": "Brother-in-law"},
        "SISTER_IN_LAW": {"ta": "அண்ணி / கொழுந்தியாள்", "en": "Sister-in-law"},
        "SON_IN_LAW": {"ta": "மருமகன்", "en": "Son-in-law"},
        "DAUGHTER_IN_LAW": {"ta": "மருமகள்", "en": "Daughter-in-law"},
        "NEPHEW": {"ta": "மருமகன்", "en": "Nephew"},
        "NIECE": {"ta": "மருமகள்", "en": "Niece"},
        "GRANDSON": {"ta": "பேரன்", "en": "Grandson"},
        "GRANDDAUGHTER": {"ta": "பேத்தி", "en": "Granddaughter"},
        "COUSIN_MALE": {"ta": "உறவினர் (ஆண்)", "en": "Cousin (Male)"},
        "COUSIN_FEMALE": {"ta": "உறவினர் (பெண்)", "en": "Cousin (Female)"},
        "STEP_FATHER": {"ta": "மாற்றாந்தந்தை", "en": "Step Father"},
        "STEP_MOTHER": {"ta": "மாற்றாந்தாய்", "en": "Step Mother"},
        "STEP_BROTHER": {"ta": "மாற்றாஞ்சகோதரன்", "en": "Step Brother"},
        "STEP_SISTER": {"ta": "மாற்றாஞ்சகோதரி", "en": "Step Sister"},
        "UNCLE": {"ta": "மாமா / பெரியப்பா / சித்தப்பா", "en": "Uncle"},
        "AUNT": {"ta": "அத்தை / பெரியம்மா / சித்தி", "en": "Aunt"},
    }
    
    GENDER_MAP = {
        "PAATI": "F",
        "THATHA": "M",
        "PERIYAPPA": "M",
        "PERIYAMMA": "F",
        "CHITHAPPA": "M",
        "CHITHI": "F",
        "MAMA": "M",
        "ATHAI": "F",
        "ANNA": "M",
        "AKKA": "F",
        "THAMBI": "M",
        "THANGAI": "F",
        "KOLUNTHANAR": "M",
        "KOLUNTHIYAZH": "F",
        "ATHAN": "M",
        "ANNI": "F",
        "MARUMAGAN": "M",
        "MARUMAGAL": "F",
        "PERAN": "M",
        "PETTHI": "F",
        "MAITHUNAR": "M",
        "MAGAN": 'M',
        "MAGHAZH": "F",
        "FATHER_ELDER_BROTHER": "M",
        "FATHER_YOUNGER_BROTHER": "M",
        "FATHER_SISTER": "F",
        "MOTHER_BROTHER": "M",
        "MOTHER_ELDER_SISTER": "F",
        "MOTHER_YOUNGER_SISTER": "F",
        "FATHER_IN_LAW": "M",
        "MOTHER_IN_LAW": "F",
        "SON_IN_LAW": "M",
        "DAUGHTER_IN_LAW": "F",
        "NEPHEW": "M",
        "NIECE": "F",
        "GRANDSON": "M",
        "GRANDDAUGHTER": "F",
        "COUSIN_MALE": "M",
        "COUSIN_FEMALE": "F",
        "STEP_FATHER": "M",
        "STEP_MOTHER": "F",
        "STEP_BROTHER": "M",
        "STEP_SISTER": "F",
        "UNCLE": "M",
        "AUNT": "F",
    }
    
    # Cache for labels
    _labels_cache = None
    _cache_timestamp = None
    CACHE_DURATION = 300  # 5 minutes

    @classmethod
    def get_all(cls, language="en"):
        """
        Get all labels in specified language with caching.
        
        Args:
            language: Language code ('en' or 'ta')
        
        Returns:
            List of dictionaries with address_code and label
        """
        # Validate language
        if language not in ['en', 'ta']:
            logger.warning(f"Invalid language '{language}', defaulting to 'en'")
            language = 'en'
        
        # Check cache
        current_time = datetime.now().timestamp()
        if cls._labels_cache and cls._cache_timestamp:
            if current_time - cls._cache_timestamp < cls.CACHE_DURATION:
                return cls._labels_cache.get(language, [])
        
        try:
            labels = [
                {
                    "address_code": code,
                    "label": data.get(language, data["en"])
                }
                for code, data in cls.LABELS.items()
            ]
            
            # Update cache
            if not cls._labels_cache:
                cls._labels_cache = {}
            cls._labels_cache[language] = labels
            cls._cache_timestamp = current_time
            
            return labels
            
        except Exception as e:
            logger.error(f"Error in get_all labels: {str(e)}", exc_info=True)
            return []

    @classmethod
    def get_gender(cls, code):
        """
        Get gender for a relation code with error handling.
        
        Args:
            code: Relation code (e.g., 'THATHA')
        
        Returns:
            Gender code ('M', 'F', or None if not found)
        """
        try:
            if not code:
                logger.warning("Empty code provided to get_gender")
                return None
            
            gender = cls.GENDER_MAP.get(code.upper())
            if gender is None:
                logger.debug(f"No gender mapping found for code: {code}")
            
            return gender
            
        except Exception as e:
            logger.error(f"Error in get_gender for code {code}: {str(e)}")
            return None
    
    @classmethod
    def get_label(cls, code, language="en"):
        """
        Get single label with error handling.
        
        Args:
            code: Relation code
            language: Language code
        
        Returns:
            Label string or None if not found
        """
        try:
            if not code:
                return None
            
            code = code.upper()
            if code not in cls.LABELS:
                logger.warning(f"Label not found for code: {code}")
                return None
            
            return cls.LABELS[code].get(language, cls.LABELS[code]['en'])
            
        except Exception as e:
            logger.error(f"Error getting label for {code}: {str(e)}")
            return None


# services/relation_automation.py
from typing import List, Dict, Optional, Tuple, Any
from django.db.models import Q
from datetime import datetime
from .models import FixedRelation

try:
    from apps.genealogy.models import Person, PersonRelation
except ImportError:
    logger.warning("Genealogy models not available, some features will be limited")
    Person = None
    PersonRelation = None


# services/relation_automation.py
from typing import List, Dict, Optional, Tuple, Any
from django.db.models import Q
from django.core.cache import cache
from datetime import datetime
import logging
from .models import FixedRelation
from .services import RelationLabelService, AshramamLabelService

try:
    from apps.genealogy.models import Person, PersonRelation
except ImportError:
    logger.warning("Genealogy models not available, some features will be limited")
    Person = None
    PersonRelation = None

logger = logging.getLogger(__name__)


class RelationAutomationEngine:
    """Main engine for automated relation calculation from click paths with full profile override support."""
    
    # Enhanced composition rules - COMPLETE SET
    RELATION_COMPOSITION_RULES = {
        # Grandparents (Level 2)
        ('FATHER', 'FATHER'): 'GRANDFATHER',
        ('FATHER', 'MOTHER'): 'GRANDMOTHER',
        ('MOTHER', 'FATHER'): 'GRANDFATHER',
        ('MOTHER', 'MOTHER'): 'GRANDMOTHER',
        
        # Parents' siblings (Uncles/Aunts) - Level 2
        ('FATHER', 'BROTHER'): 'FATHER_BROTHER',
        ('FATHER', 'SISTER'): 'FATHER_SISTER',
        ('FATHER', 'ELDER_BROTHER'): 'FATHER_ELDER_BROTHER',
        ('FATHER', 'YOUNGER_BROTHER'): 'FATHER_YOUNGER_BROTHER',
        ('FATHER', 'ELDER_SISTER'): 'FATHER_ELDER_SISTER',
        ('FATHER', 'YOUNGER_SISTER'): 'FATHER_YOUNGER_SISTER',
        
        ('MOTHER', 'BROTHER'): 'MOTHER_BROTHER',
        ('MOTHER', 'SISTER'): 'MOTHER_SISTER',
        ('MOTHER', 'ELDER_SISTER'): 'MOTHER_ELDER_SISTER',
        ('MOTHER', 'YOUNGER_SISTER'): 'MOTHER_YOUNGER_SISTER',
        
        # Parents' spouses (Step-parents) - Level 2
        ('FATHER', 'WIFE'): 'STEP_MOTHER',
        ('MOTHER', 'HUSBAND'): 'STEP_FATHER',
        
        # Siblings - direct
        ('PARENT', 'SON'): 'BROTHER',
        ('PARENT', 'DAUGHTER'): 'SISTER',
        
        # Siblings' spouses (In-laws) - Level 2
        ('BROTHER', 'WIFE'): 'SISTER_IN_LAW',
        ('ELDER_BROTHER', 'WIFE'): 'SISTER_IN_LAW',
        ('YOUNGER_BROTHER', 'WIFE'): 'SISTER_IN_LAW',
        
        ('SISTER', 'HUSBAND'): 'BROTHER_IN_LAW',
        ('ELDER_SISTER', 'HUSBAND'): 'BROTHER_IN_LAW',
        ('YOUNGER_SISTER', 'HUSBAND'): 'BROTHER_IN_LAW',
        
        # Children's spouses - Level 2
        ('SON', 'WIFE'): 'DAUGHTER_IN_LAW',
        ('DAUGHTER', 'HUSBAND'): 'SON_IN_LAW',
        
        # Spouses' relatives - Level 2
        ('HUSBAND', 'FATHER'): 'FATHER_IN_LAW',
        ('HUSBAND', 'MOTHER'): 'MOTHER_IN_LAW',
        ('HUSBAND', 'BROTHER'): 'BROTHER_IN_LAW',
        ('HUSBAND', 'SISTER'): 'SISTER_IN_LAW',
        
        ('WIFE', 'FATHER'): 'FATHER_IN_LAW',
        ('WIFE', 'MOTHER'): 'MOTHER_IN_LAW',
        ('WIFE', 'BROTHER'): 'BROTHER_IN_LAW',
        ('WIFE', 'SISTER'): 'SISTER_IN_LAW',
        
        # Nephews/Nieces - Level 2
        ('BROTHER', 'SON'): 'NEPHEW',
        ('BROTHER', 'DAUGHTER'): 'NIECE',
        ('ELDER_BROTHER', 'SON'): 'NEPHEW',
        ('ELDER_BROTHER', 'DAUGHTER'): 'NIECE',
        ('YOUNGER_BROTHER', 'SON'): 'NEPHEW',
        ('YOUNGER_BROTHER', 'DAUGHTER'): 'NIECE',
        
        ('SISTER', 'SON'): 'NEPHEW',
        ('SISTER', 'DAUGHTER'): 'NIECE',
        ('ELDER_SISTER', 'SON'): 'NEPHEW',
        ('ELDER_SISTER', 'DAUGHTER'): 'NIECE',
        ('YOUNGER_SISTER', 'SON'): 'NEPHEW',
        ('YOUNGER_SISTER', 'DAUGHTER'): 'NIECE',
        
        # Grandchildren - Level 2
        ('SON', 'SON'): 'GRANDSON',
        ('SON', 'DAUGHTER'): 'GRANDDAUGHTER',
        ('DAUGHTER', 'SON'): 'GRANDSON',
        ('DAUGHTER', 'DAUGHTER'): 'GRANDDAUGHTER',
        
        # Cousins (Level 3: Uncle/Aunt → Child)
        ('FATHER_BROTHER', 'SON'): 'COUSIN_MALE',
        ('FATHER_BROTHER', 'DAUGHTER'): 'COUSIN_FEMALE',
        ('FATHER_SISTER', 'SON'): 'COUSIN_MALE',
        ('FATHER_SISTER', 'DAUGHTER'): 'COUSIN_FEMALE',
        ('MOTHER_BROTHER', 'SON'): 'COUSIN_MALE',
        ('MOTHER_BROTHER', 'DAUGHTER'): 'COUSIN_FEMALE',
        ('MOTHER_SISTER', 'SON'): 'COUSIN_MALE',
        ('MOTHER_SISTER', 'DAUGHTER'): 'COUSIN_FEMALE',
        
        # Step-siblings (Level 3: Step-parent → Child)
        ('STEP_MOTHER', 'SON'): 'STEP_BROTHER',
        ('STEP_MOTHER', 'DAUGHTER'): 'STEP_SISTER',
        ('STEP_FATHER', 'SON'): 'STEP_BROTHER',
        ('STEP_FATHER', 'DAUGHTER'): 'STEP_SISTER',
        
        # Multi-level compositions (Level 3+)
        ('GRANDFATHER', 'SON'): 'UNCLE',
        ('GRANDFATHER', 'DAUGHTER'): 'AUNT',
        ('GRANDMOTHER', 'SON'): 'UNCLE',
        ('GRANDMOTHER', 'DAUGHTER'): 'AUNT',
    }
    
    # Tamil-specific mapping with your codes
    TAMIL_REFINEMENT_MAP = {
        # Paternal side
        'FATHER_BROTHER_ELDER': 'FATHER_ELDER_BROTHER',
        'FATHER_BROTHER_YOUNGER': 'FATHER_YOUNGER_BROTHER',
        'FATHER_SISTER_ELDER': 'FATHER_ELDER_SISTER',
        'FATHER_SISTER_YOUNGER': 'FATHER_YOUNGER_SISTER',
        
        # Maternal side
        'MOTHER_BROTHER': 'MOTHER_BROTHER',
        'MOTHER_SISTER_ELDER': 'MOTHER_ELDER_SISTER',
        'MOTHER_SISTER_YOUNGER': 'MOTHER_YOUNGER_SISTER',
        
        # Grandparents
        'GRANDFATHER': 'GRANDFATHER',
        'GRANDMOTHER': 'GRANDMOTHER',
        
        # Siblings
        'BROTHER': 'BROTHER',
        'SISTER': 'SISTER',
        'BROTHER_ELDER': 'ELDER_BROTHER',
        'BROTHER_YOUNGER': 'YOUNGER_BROTHER',
        'SISTER_ELDER': 'ELDER_SISTER',
        'SISTER_YOUNGER': 'YOUNGER_SISTER',
        
        # Step-parents
        'STEP_MOTHER': 'STEP_MOTHER',
        'STEP_FATHER': 'STEP_FATHER',
        
        # Step-siblings
        'STEP_BROTHER': 'STEP_BROTHER',
        'STEP_SISTER': 'STEP_SISTER',
        
        # Spouses
        'HUSBAND': 'HUSBAND',
        'WIFE': 'WIFE',
        
        # In-laws
        'BROTHER_IN_LAW': 'BROTHER_IN_LAW',
        'SISTER_IN_LAW': 'SISTER_IN_LAW',
        'FATHER_IN_LAW': 'FATHER_IN_LAW',
        'MOTHER_IN_LAW': 'MOTHER_IN_LAW',
        
        # Children's spouses
        'SON_IN_LAW': 'SON_IN_LAW',
        'DAUGHTER_IN_LAW': 'DAUGHTER_IN_LAW',
        
        # Nephews/Nieces
        'NEPHEW': 'NEPHEW',
        'NIECE': 'NIECE',
        
        # Grandchildren
        'GRANDSON': 'GRANDSON',
        'GRANDDAUGHTER': 'GRANDDAUGHTER',
        
        # Cousins
        'COUSIN_MALE': 'COUSIN_MALE',
        'COUSIN_FEMALE': 'COUSIN_FEMALE',
        
        # Generic
        'UNCLE': 'UNCLE',
        'AUNT': 'AUNT',
    }
    
    # Extended normalization mapping
    RELATION_ALIASES = {
        # Step relationships
        'stepfather': 'STEP_FATHER',
        'stepdad': 'STEP_FATHER',
        'stepmother': 'STEP_MOTHER',
        'stepmom': 'STEP_MOTHER',
        'stepmum': 'STEP_MOTHER',
        
        # Step siblings
        'stepbrother': 'STEP_BROTHER',
        'stepbro': 'STEP_BROTHER',
        'stepsister': 'STEP_SISTER',
        'stepsister': 'STEP_SISTER',
        
        # In-laws
        'fatherinlaw': 'FATHER_IN_LAW',
        'father-in-law': 'FATHER_IN_LAW',
        'motherinlaw': 'MOTHER_IN_LAW',
        'mother-in-law': 'MOTHER_IN_LAW',
        'brotherinlaw': 'BROTHER_IN_LAW',
        'brother-in-law': 'BROTHER_IN_LAW',
        'sisterinlaw': 'SISTER_IN_LAW',
        'sister-in-law': 'SISTER_IN_LAW',
        
        # Cousins
        'cousin': 'COUSIN_MALE',
        'cousinbrother': 'COUSIN_MALE',
        'cousin-sister': 'COUSIN_FEMALE',
        
        # Tamil step relationships
        'மாற்றாந் தந்தை': 'STEP_FATHER',
        'மாற்றாந் தாய்': 'STEP_MOTHER',
        'மாற்றாந் சகோதரன்': 'STEP_BROTHER',
        'மாற்றாந் சகோதரி': 'STEP_SISTER',
    }
    
    # Cache for normalized inputs
    _normalization_cache = {}
    _composition_cache = {}
    
    @classmethod
    def calculate_relation_from_path(
        cls,
        from_person: Optional[Any],
        path_elements: List[str],
        to_person: Optional[Any] = None,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate relation from click path with multi-level support and profile overrides.
        
        Args:
            from_person: Starting person (can be None for testing)
            path_elements: List of relation steps
            to_person: Target person (optional)
            context: Additional context like language, religion, caste, native, etc.
        
        Returns:
            Dictionary with relation details including localized label with profile overrides
        """
        # Initialize result structure
        result = {
            'base_relation': None,
            'refined_relation': None,
            'label': '',
            'localization_level': 'default',
            'path_used': path_elements.copy() if path_elements else [],
            'normalized_path': [],
            'composition_history': [],
            'errors': [],
            'warnings': []
        }
        
        # Input validation
        if not path_elements:
            logger.warning("Empty path elements provided")
            result['base_relation'] = 'SELF'
            result['refined_relation'] = 'SELF'
            result['label'] = 'Self'
            result['warnings'].append('Empty path, defaulting to SELF')
            return result
        
        context = context or {}
        
        try:
            # Step 1: Normalize and compose with multi-level support
            current_code = None
            normalized_path = []
            composition_history = []
            
            for i, element in enumerate(path_elements):
                try:
                    element_code = cls._normalize_relation_input(element)
                    normalized_path.append(element_code)
                    
                    if current_code is None:
                        current_code = element_code
                        continue
                    
                    # Check for direct composition rule
                    composition_key = (current_code, element_code)
                    
                    if composition_key in cls.RELATION_COMPOSITION_RULES:
                        new_code = cls.RELATION_COMPOSITION_RULES[composition_key]
                        composition_history.append(f"{current_code}+{element_code}={new_code}")
                        current_code = new_code
                    else:
                        # Check for generic parent substitution
                        if element_code in ['SON', 'DAUGHTER']:
                            if current_code.startswith(('FATHER_', 'MOTHER_', 'UNCLE', 'AUNT')):
                                if element_code == 'SON':
                                    current_code = 'COUSIN_MALE'
                                else:
                                    current_code = 'COUSIN_FEMALE'
                                composition_history.append(f"{composition_key[0]}+{element_code}=COUSIN")
                            else:
                                # Generic composition
                                current_code = f"{current_code}_{element_code}"
                                composition_history.append(f"{composition_key[0]}+{element_code}=COMPOSED")
                        else:
                            # Generic fallback composition
                            current_code = f"{current_code}_{element_code}"
                            composition_history.append(f"{composition_key[0]}+{element_code}=COMPOSED")
                            
                except Exception as e:
                    error_msg = f"Error processing path element {i} ('{element}'): {str(e)}"
                    logger.error(error_msg)
                    result['errors'].append(error_msg)
                    # Continue with next element using current code
            
            result['base_relation'] = current_code
            result['normalized_path'] = normalized_path
            result['composition_history'] = composition_history
            
            # Step 2: Apply Tamil refinements
            try:
                refined_code = cls._apply_refinements(
                    base_code=current_code,
                    path_elements=normalized_path,
                    from_person=from_person,
                    to_person=to_person,
                    context=context
                )
                result['refined_relation'] = refined_code
            except Exception as e:
                error_msg = f"Error applying refinements: {str(e)}"
                logger.error(error_msg)
                result['errors'].append(error_msg)
                result['refined_relation'] = current_code
            
            # Step 3: Get localized label using the enhanced service with FULL profile context
            try:
                # Extract ALL profile fields from context (with defaults)
                language = context.get('language', 'ta')
                religion = context.get('religion', '')
                caste = context.get('caste', '')
                family_name = context.get('family_name', '')
                native = context.get('native', '')
                present_city = context.get('present_city', '')
                taluk = context.get('taluk', '')
                district = context.get('district', '')
                state = context.get('state', '')
                nationality = context.get('nationality', '')
                
                # Log the context being used for debugging
                logger.debug(f"Getting label for {result['refined_relation']} with context: lang={language}, religion={religion}, caste={caste}, family={family_name}, native={native}")
                
                # Get label from RelationLabelService (which includes profile overrides)
                label_info = RelationLabelService.get_relation_label(
                    relation_code=result['refined_relation'],
                    language=language,
                    religion=religion,
                    caste=caste,
                    family_name=family_name,
                    native=native,
                    present_city=present_city,
                    taluk=taluk,
                    district=district,
                    state=state,
                    nationality=nationality,
                    use_cache=True
                )
                
                result['label'] = label_info['label']
                result['localization_level'] = label_info.get('level', 'default')
                result['label_source'] = label_info.get('source', 'unknown')
                result['label_metadata'] = label_info.get('metadata', {})
                
                logger.debug(f"Resolved label: {result['label']} at level {result['localization_level']}")
                
            except Exception as e:
                error_msg = f"Error getting localized label: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result['errors'].append(error_msg)
                # Fallback to AshramamLabelService or raw code
                try:
                    result['label'] = AshramamLabelService.get_label(
                        result['refined_relation'], 
                        language
                    ) or result['refined_relation']
                except:
                    result['label'] = result['refined_relation']
            
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error in calculate_relation_from_path: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result['errors'].append(error_msg)
            result['base_relation'] = 'ERROR'
            result['refined_relation'] = 'ERROR'
            result['label'] = 'Error'
            return result
    
    @classmethod
    def _normalize_relation_input(cls, input_str: str) -> str:
        """Convert inputs to standardized relation codes with caching."""
        # Check cache first
        cache_key = f"norm:{input_str}"
        if cache_key in cls._normalization_cache:
            return cls._normalization_cache[cache_key]
        
        try:
            if not isinstance(input_str, str):
                result = str(input_str).upper()
                cls._normalization_cache[cache_key] = result
                return result
            
            # First check extended aliases
            key = input_str.lower().replace(' ', '').replace('-', '').replace('_', '')
            if key in cls.RELATION_ALIASES:
                result = cls.RELATION_ALIASES[key]
                cls._normalization_cache[cache_key] = result
                return result
            
            mapping = {
                # Basic relations
                'father': 'FATHER', 'dad': 'FATHER', 'papa': 'FATHER', 'தந்தை': 'FATHER',
                'mother': 'MOTHER', 'mom': 'MOTHER', 'amma': 'MOTHER', 'தாய்': 'MOTHER',
                
                # Siblings with age
                'brother': 'BROTHER',
                'elderbrother': 'ELDER_BROTHER', 'elder brother': 'ELDER_BROTHER',
                'youngerbrother': 'YOUNGER_BROTHER', 'younger brother': 'YOUNGER_BROTHER',
                
                'sister': 'SISTER',
                'eldersister': 'ELDER_SISTER', 'elder sister': 'ELDER_SISTER',
                'youngersister': 'YOUNGER_SISTER', 'younger sister': 'YOUNGER_SISTER',
                
                # Children
                'son': 'SON', 'மகன்': 'SON',
                'daughter': 'DAUGHTER', 'மகள்': 'DAUGHTER',
                
                # Spouses
                'husband': 'HUSBAND', 'கணவன்': 'HUSBAND',
                'wife': 'WIFE', 'மனைவி': 'WIFE',
                
                # Grandparents
                'grandfather': 'GRANDFATHER', 'தாத்தா': 'GRANDFATHER',
                'grandmother': 'GRANDMOTHER', 'பாட்டி': 'GRANDMOTHER',
                
                # Tamil variants (direct codes)
                'அப்பா': 'FATHER',
                'அம்மா': 'MOTHER',
                'அண்ணன்': 'ELDER_BROTHER',
                'அக்கா': 'ELDER_SISTER',
                'தம்பி': 'YOUNGER_BROTHER',
                'தங்கை': 'YOUNGER_SISTER',
                
                # Uncles/Aunts (Tamil)
                'பெரியப்பா': 'FATHER_ELDER_BROTHER',
                'சித்தப்பா': 'FATHER_YOUNGER_BROTHER',
                'அத்தை': 'FATHER_SISTER',
                'மாமா': 'MOTHER_BROTHER',
                'பெரியம்மா': 'MOTHER_ELDER_SISTER',
                'சித்தி': 'MOTHER_YOUNGER_SISTER',
                
                # In-laws (Tamil)
                'மாமனார்': 'FATHER_IN_LAW',
                'மாமியார்': 'MOTHER_IN_LAW',
                'அத்தான்': 'BROTHER_IN_LAW',
                'அண்ணி': 'SISTER_IN_LAW',
                
                # Additional relations
                'stepfather': 'STEP_FATHER',
                'stepmother': 'STEP_MOTHER',
                'stepbrother': 'STEP_BROTHER',
                'stepsister': 'STEP_SISTER',
                'nephew': 'NEPHEW',
                'niece': 'NIECE',
                'grandson': 'GRANDSON',
                'granddaughter': 'GRANDDAUGHTER',
                'cousin': 'COUSIN_MALE',
            }
            
            key = input_str.lower().replace(' ', '')
            if key in mapping:
                result = mapping[key]
                cls._normalization_cache[cache_key] = result
                return result
            
            # Default: uppercase
            result = input_str.upper()
            cls._normalization_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error normalizing input '{input_str}': {str(e)}")
            return str(input_str).upper()
    
    @classmethod
    def _apply_refinements(
        cls,
        base_code: str,
        path_elements: List[str],
        from_person: Optional[Any] = None,
        to_person: Optional[Any] = None,
        context: Optional[Dict] = None
    ) -> str:
        """Apply Tamil-specific refinements with age comparison."""
        
        if not base_code:
            return base_code
        
        try:
            context = context or {}
            
            # If it's already a standard code, return as is
            if base_code in cls.TAMIL_REFINEMENT_MAP.values():
                return base_code
            
            # Determine family side
            family_side = None
            if len(path_elements) > 0:
                first_relation = path_elements[0]
                if first_relation in ['FATHER', 'FATHER_ELDER_BROTHER', 'FATHER_YOUNGER_BROTHER', 'FATHER_SISTER']:
                    family_side = 'PATERNAL'
                elif first_relation in ['MOTHER', 'MOTHER_BROTHER', 'MOTHER_ELDER_SISTER', 'MOTHER_YOUNGER_SISTER']:
                    family_side = 'MATERNAL'
            
            # Get age context
            age_context = cls._get_age_context(from_person, to_person)
            
            # Special handling for step relationships
            if base_code == 'STEP_MOTHER':
                if len(path_elements) == 2 and path_elements[0] == 'FATHER':
                    return 'STEP_MOTHER'
            
            elif base_code == 'STEP_FATHER':
                if len(path_elements) == 2 and path_elements[0] == 'MOTHER':
                    return 'STEP_FATHER'
            
            # Handle parent's siblings with age context
            if base_code == 'FATHER_BROTHER':
                if family_side == 'PATERNAL':
                    if age_context == 'ELDER':
                        return 'FATHER_ELDER_BROTHER'
                    elif age_context == 'YOUNGER':
                        return 'FATHER_YOUNGER_BROTHER'
            
            elif base_code == 'FATHER_SISTER':
                if family_side == 'PATERNAL':
                    if age_context == 'ELDER':
                        return 'FATHER_ELDER_SISTER'
                    elif age_context == 'YOUNGER':
                        return 'FATHER_YOUNGER_SISTER'
            
            elif base_code == 'MOTHER_SISTER':
                if family_side == 'MATERNAL':
                    if age_context == 'ELDER':
                        return 'MOTHER_ELDER_SISTER'
                    elif age_context == 'YOUNGER':
                        return 'MOTHER_YOUNGER_SISTER'
            
            # Handle direct siblings with age
            elif base_code in ['BROTHER', 'SISTER'] and len(path_elements) == 1:
                if base_code == 'BROTHER':
                    if age_context == 'ELDER':
                        return 'ELDER_BROTHER'
                    elif age_context == 'YOUNGER':
                        return 'YOUNGER_BROTHER'
                elif base_code == 'SISTER':
                    if age_context == 'ELDER':
                        return 'ELDER_SISTER'
                    elif age_context == 'YOUNGER':
                        return 'YOUNGER_SISTER'
            
            # Handle generic mappings
            if base_code in cls.TAMIL_REFINEMENT_MAP:
                return cls.TAMIL_REFINEMENT_MAP[base_code]
            
            return base_code
            
        except Exception as e:
            logger.error(f"Error in _apply_refinements for {base_code}: {str(e)}")
            return base_code
    
    @classmethod
    def _get_age_context(cls, from_person: Optional[Any], to_person: Optional[Any] = None) -> Optional[str]:
        """Determine age context between two persons."""
        if not to_person or not from_person:
            return None
            
        try:
            if hasattr(from_person, 'date_of_birth') and hasattr(to_person, 'date_of_birth'):
                if from_person.date_of_birth and to_person.date_of_birth:
                    if from_person.date_of_birth < to_person.date_of_birth:
                        return 'ELDER'  # from_person is elder
                    elif from_person.date_of_birth > to_person.date_of_birth:
                        return 'YOUNGER'  # from_person is younger
        except (AttributeError, TypeError) as e:
            logger.debug(f"Could not determine age context: {str(e)}")
        
        return None
    
    @classmethod
    def get_relation_with_user_context(
        cls,
        from_person: Any,
        path_elements: List[str],
        user_profile: Any,
        to_person: Optional[Any] = None
    ) -> Dict:
        """
        Convenience method that automatically extracts context from user profile.
        
        Args:
            from_person: Starting person
            path_elements: List of relation steps
            user_profile: User's profile object with all fields
            to_person: Target person (optional)
        
        Returns:
            Dictionary with relation details including profile-based labels
        """
        # Extract all profile fields
        context = {
            'language': getattr(user_profile, 'preferred_language', 'ta'),
            'religion': getattr(user_profile, 'religion', ''),
            'caste': getattr(user_profile, 'caste', ''),
            'family_name': getattr(user_profile, 'familyname1', ''),
            'native': getattr(user_profile, 'native', ''),
            'present_city': getattr(user_profile, 'present_city', ''),
            'taluk': getattr(user_profile, 'taluk', ''),
            'district': getattr(user_profile, 'district', ''),
            'state': getattr(user_profile, 'state', ''),
            'nationality': getattr(user_profile, 'nationality', '')
        }
        
        return cls.calculate_relation_from_path(
            from_person=from_person,
            path_elements=path_elements,
            to_person=to_person,
            context=context
        )
    
    @classmethod
    def generate_relation_examples(cls) -> List[Dict]:
        """Generate comprehensive examples for testing."""
        examples = [
            # Level 1: Direct
            {'path': ['father'], 'expected': 'FATHER', 'description': 'Direct father'},
            {'path': ['mother'], 'expected': 'MOTHER', 'description': 'Direct mother'},
            
            # Level 2: Two steps
            {'path': ['father', 'father'], 'expected': 'GRANDFATHER', 'description': 'Paternal grandfather'},
            {'path': ['mother', 'father'], 'expected': 'GRANDFATHER', 'description': 'Maternal grandfather'},
            {'path': ['father', 'mother'], 'expected': 'GRANDMOTHER', 'description': 'Paternal grandmother'},
            {'path': ['mother', 'mother'], 'expected': 'GRANDMOTHER', 'description': 'Maternal grandmother'},
            
            # Father's wife (step-mother)
            {'path': ['father', 'wife'], 'expected': 'STEP_MOTHER', 'description': 'Father\'s wife (step-mother)'},
            
            # Mother's husband (step-father)
            {'path': ['mother', 'husband'], 'expected': 'STEP_FATHER', 'description': 'Mother\'s husband (step-father)'},
            
            # Father's siblings
            {'path': ['father', 'elder brother'], 'expected': 'FATHER_ELDER_BROTHER', 'description': 'Father\'s elder brother'},
            {'path': ['father', 'younger brother'], 'expected': 'FATHER_YOUNGER_BROTHER', 'description': 'Father\'s younger brother'},
            {'path': ['father', 'sister'], 'expected': 'FATHER_SISTER', 'description': 'Father\'s sister'},
            
            # Mother's siblings
            {'path': ['mother', 'brother'], 'expected': 'MOTHER_BROTHER', 'description': 'Mother\'s brother'},
            {'path': ['mother', 'elder sister'], 'expected': 'MOTHER_ELDER_SISTER', 'description': 'Mother\'s elder sister'},
            {'path': ['mother', 'younger sister'], 'expected': 'MOTHER_YOUNGER_SISTER', 'description': 'Mother\'s younger sister'},
            
            # Sibling's spouse
            {'path': ['elder brother', 'wife'], 'expected': 'SISTER_IN_LAW', 'description': 'Elder brother\'s wife'},
            {'path': ['younger sister', 'husband'], 'expected': 'BROTHER_IN_LAW', 'description': 'Younger sister\'s husband'},
            
            # Children's spouses
            {'path': ['son', 'wife'], 'expected': 'DAUGHTER_IN_LAW', 'description': 'Son\'s wife'},
            {'path': ['daughter', 'husband'], 'expected': 'SON_IN_LAW', 'description': 'Daughter\'s husband'},
            
            # Level 3: Three steps
            {'path': ['father', 'elder brother', 'son'], 'expected': 'COUSIN_MALE', 'description': 'Father\'s elder brother\'s son (cousin)'},
            {'path': ['mother', 'sister', 'daughter'], 'expected': 'COUSIN_FEMALE', 'description': 'Mother\'s sister\'s daughter (cousin)'},
            
            # Step-siblings
            {'path': ['step father', 'son'], 'expected': 'STEP_BROTHER', 'description': 'Step-father\'s son'},
            {'path': ['step mother', 'daughter'], 'expected': 'STEP_SISTER', 'description': 'Step-mother\'s daughter'},
            
            # Spouse's relatives
            {'path': ['husband', 'father'], 'expected': 'FATHER_IN_LAW', 'description': 'Husband\'s father'},
            {'path': ['wife', 'mother'], 'expected': 'MOTHER_IN_LAW', 'description': 'Wife\'s mother'},
            
            # Nephews/Nieces
            {'path': ['elder brother', 'son'], 'expected': 'NEPHEW', 'description': 'Elder brother\'s son'},
            {'path': ['younger sister', 'daughter'], 'expected': 'NIECE', 'description': 'Younger sister\'s daughter'},
            
            # Grandchildren
            {'path': ['son', 'son'], 'expected': 'GRANDSON', 'description': 'Son\'s son'},
            {'path': ['daughter', 'daughter'], 'expected': 'GRANDDAUGHTER', 'description': 'Daughter\'s daughter'},
            
            # Tamil specific examples
            {'path': ['அப்பா', 'அண்ணன்'], 'expected': 'FATHER_ELDER_BROTHER', 'description': 'Father\'s elder brother (Tamil)'},
            {'path': ['அம்மா', 'தங்கை'], 'expected': 'MOTHER_YOUNGER_SISTER', 'description': 'Mother\'s younger sister (Tamil)'},
        ]
        
        # Add validation
        for example in examples:
            try:
                result = cls.calculate_relation_from_path(
                    from_person=None,
                    path_elements=example['path'],
                    context={'test_mode': True, 'language': 'ta'}
                )
                example['actual'] = result.get('refined_relation')
                example['label'] = result.get('label')
                example['success'] = example['actual'] == example['expected']
            except Exception as e:
                example['actual'] = 'ERROR'
                example['success'] = False
                example['error'] = str(e)
        
        return examples


# Utility function to clear caches
def clear_relation_caches():
    """Clear all relation service caches."""
    try:
        RelationAutomationEngine._normalization_cache.clear()
        RelationAutomationEngine._composition_cache.clear()
        
        # Clear AshramamLabelService cache if it exists
        if hasattr(AshramamLabelService, '_labels_cache'):
            AshramamLabelService._labels_cache = None
            AshramamLabelService._cache_timestamp = None
        
        # Clear Django cache
        from django.core.cache import cache
        cache.clear()
        
        logger.info("All relation caches cleared")
    except Exception as e:
        logger.error(f"Error clearing caches: {str(e)}")