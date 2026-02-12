"""
Core service for relation label resolution.
Implements the 4-level fallback system.
"""
from typing import Optional, Dict, Any
from django.db.models import Q
from .models import (
    FixedRelation,
    RelationFamily,
    RelationCaste,
    RelationLanguageReligion
)

class RelationLabelService:
    """
    Service for resolving relationship labels using 4-level fallback system.
    
    Resolution order (STRICT):
    1. RelationFamily
    2. RelationCaste
    3. RelationLanguageReligion
    4. FixedRelation default
    """
    
    @staticmethod
    def get_relation_label(
        relation_code: str,
        language: str,
        religion: str,
        caste: str,
        family_name: Optional[str] = None,
        gender_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get relation label using 4-level fallback system.
        
        Args:
            relation_code: Fixed relation code (e.g., 'FATHER')
            language: Preferred language (e.g., 'ta', 'en')
            religion: User's religion
            caste: User's caste
            family_name: Family name for level 1 override
            gender_context: Gender context for language-specific forms
        
        Returns:
            Dictionary with label and metadata
        """
        try:
            relation = FixedRelation.objects.get(relation_code=relation_code)
        except FixedRelation.DoesNotExist:
            return {
                'label': relation_code,
                'level': 'not_found',
                'relation_code': relation_code
            }
        
        # Level 1: Family-specific override
        if family_name:
            try:
                family_label = RelationFamily.objects.get(
                    relation=relation,
                    language=language,
                    religion=religion,
                    caste=caste,
                    family=family_name
                )
                return {
                    'label': family_label.label,
                    'level': 'family',
                    'relation_code': relation_code,
                    'source': 'family_override'
                }
            except RelationFamily.DoesNotExist:
                pass
        
        # Level 2: Caste-specific label
        try:
            caste_label = RelationCaste.objects.get(
                relation=relation,
                language=language,
                religion=religion,
                caste=caste
            )
            return {
                'label': caste_label.label,
                'level': 'caste',
                'relation_code': relation_code,
                'source': 'caste_override'
            }
        except RelationCaste.DoesNotExist:
            pass
        
        # Level 3: Language + Religion label
        try:
            lang_religion_label = RelationLanguageReligion.objects.get(
                relation=relation,
                language=language,
                religion=religion
            )
            return {
                'label': lang_religion_label.label,
                'level': 'language_religion',
                'relation_code': relation_code,
                'source': 'religion_override'
            }
        except RelationLanguageReligion.DoesNotExist:
            pass
        
        # Level 4: Fixed relation default
        if language.lower() == 'ta':
            label = relation.default_tamil
        else:
            label = relation.default_english
        
        return {
            'label': label,
            'level': 'default',
            'relation_code': relation_code,
            'source': 'system_default'
        }
    
    @staticmethod
    def get_all_labels_for_context(
        language: str,
        religion: str,
        caste: str,
        family_name: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get all relation labels for a given context.
        Useful for caching or pre-loading.
        """
        labels = {}
        
        # Get all fixed relations
        relations = FixedRelation.objects.all()
        
        for relation in relations:
            result = RelationLabelService.get_relation_label(
                relation_code=relation.relation_code,
                language=language,
                religion=religion,
                caste=caste,
                family_name=family_name
            )
            labels[relation.relation_code] = result['label']
        
        return labels
    
    @staticmethod
    def validate_gender_compatibility(
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
        try:
            relation = FixedRelation.objects.get(relation_code=relation_code)
        except FixedRelation.DoesNotExist:
            return False
        
        # # Check from_gender restriction
        # if relation.from_gender != 'A' and relation.from_gender != from_gender:
        #     return False
        
        # # Check to_gender restriction
        # if relation.to_gender != 'A' and relation.to_gender != to_gender:
        #     return False
        
        # Special gender-based validations
        gender_rules = {
        'FATHER': {'from_gender': 'M'},   # father's gender matters
        'MOTHER': {'from_gender': 'F'},   # mother's gender matters
        'SON': {},
        'DAUGHTER': {},
        'SISTER': {'from_gender': 'F'},
        'BROTHER':{'from_gender': 'M'},
        'HUSBAND': {'from_gender': 'M', 'to_gender': 'F'},
        'WIFE': {'from_gender': 'F', 'to_gender': 'M'},
        'YOUNGER_BROTHER': {'from_gender': 'M'},
        'ELDER_BROTHER': {'from_gender': 'M'},
        'YOUNGER_SISTER': {'from_gender': 'F'},
        'ELDER_SISTER': {'from_gender': 'F'},
    }
        
        if relation_code not in gender_rules:
            return True  # default allow for other relations

        rules = gender_rules[relation_code]

        if 'from_gender' in rules and rules['from_gender'] != from_gender:
            return False
        if 'to_gender' in rules and rules['to_gender'] != to_gender:
            return False

        return True

class ConflictDetectionService:
    """Service for detecting relation conflicts."""
    
    @staticmethod
    def detect_conflicts(from_person_id: int, to_person_id: int, relation_code: str) -> list:
        """
        Detect conflicts for a proposed relation.
        
        Returns list of conflict messages.
        """
        conflicts = []
        
        # Import here to avoid circular imports
        from apps.genealogy.models import PersonRelation
        
        # Get existing relations
        existing_relations = PersonRelation.objects.filter(
            from_person_id=from_person_id,
            to_person_id=to_person_id
        ).exclude(status='conflicted')
        
        # Check for duplicate relation
        if existing_relations.filter(relation__relation_code=relation_code).exists():
            conflicts.append("Duplicate relation already exists")
        
        # Check biological limits
        if relation_code in ['FATHER', 'MOTHER']:
            count = PersonRelation.objects.filter(
                from_person_id=from_person_id,
                relation__relation_code=relation_code,
                status='confirmed'
            ).count()
            
            # Get max instances from FixedRelation
            from .models import FixedRelation
            try:
                fixed_relation = FixedRelation.objects.get(relation_code=relation_code)
                if fixed_relation.max_instances > 0 and count >= fixed_relation.max_instances:
                    conflicts.append(f"Cannot have more than {fixed_relation.max_instances} {relation_code}")
            except FixedRelation.DoesNotExist:
                pass
        
        # Check reciprocal mismatch
        existing_reverse = PersonRelation.objects.filter(
            from_person_id=to_person_id,
            to_person_id=from_person_id,
            status='confirmed'
        )
        
        if existing_reverse.exists():
            # TODO: Check if reverse relation is compatible
            pass
        
        return conflicts
    

from django.db.models import Q
from apps.genealogy.models import PersonRelation


# 1️⃣ Relation composition table
RELATION_COMPOSITION = {
    ("ELDER_SISTER", "SON"): "NEPHEW",
    ("ELDER_SISTER", "DAUGHTER"): "NIECE",
    ("ELDER_SISTER", "HUSBAND"): "BROTHER_IN_LAW",

    ("YOUNGER_SISTER", "SON"): "NEPHEW",
    ("YOUNGER_SISTER", "DAUGHTER"): "NIECE",
    ("YOUNGER_SISTER", "HUSBAND"): "BROTHER_IN_LAW",

    ("ELDER_BROTHER", "SON"): "NEPHEW",
    ("ELDER_BROTHER", "DAUGHTER"): "NIECE",
    ("ELDER_BROTHER", "WIFE"): "SISTER_IN_LAW",

    ("YOUNGER_BROTHER", "SON"): "NEPHEW",
    ("YOUNGER_BROTHER", "DAUGHTER"): "NIECE",
    ("YOUNGER_BROTHER", "WIFE"): "SISTER_IN_LAW",
}


# 2️⃣ Direct relation finder
def get_direct_relation(from_person, to_person):
    """
    Returns relation_code ONLY if explicitly stored
    in this direction.
    """
    relation = PersonRelation.objects.filter(
        from_person=from_person,
        to_person=to_person,
        status__in=["confirmed", "pending"]
    ).select_related("relation").first()

    if not relation:
        return None

    return relation.relation.relation_code



# 3️⃣ Final resolver (THIS IS THE BRAIN)
def resolve_relation_to_me(me, root_person, member):
    """
    me           = logged-in user's Person
    root_person  = person you clicked (sister)
    member       = one member in her family
        """
        
    

    # If same person
    if member.id == me.id:
        return "SELF"
    
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
        return "CONNECTED"

    return RELATION_COMPOSITION.get(
        (base_relation, member_relation),
        "CONNECTED"
    )

class AshramamLabelService:
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
        
        "ANNA": {"ta": "அண்ணன்","en": "Elder Brother",},
        "AKKA": {"ta": "அக்கா","en": "Elder Sister",},
        "THAMBI": {"ta": "தம்பி","en": "Younger Brother",},
        "THANGAI": {"ta": "தங்கை","en": "Younger Sister"},
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
        "KOLUNTHANAR":"M",
        "KOLUNTHIYAZH":"F",
        "ATHAN":"M",
        "ANNI":"F",
        "MARUMAGAN":"M",
        "MARUMAGAL":"F",
        "PERAN":"M",
        "PETTHI":"F",
        "MAITHUNAR":"M",
        "MAGAN":'M',
        "MAGHAZH":"F"
    }

    @classmethod
    def get_all(cls, language="en"):
        return [
            {
                "address_code": code,
                "label": data.get(language, data["en"])
            }
            for code, data in cls.LABELS.items()
        ]

    @classmethod
    def get_gender(cls, code):
        return cls.LABELS.get(code, {}).get("gender")


# services/relation_automation.py
from typing import List, Dict, Optional, Tuple
from django.db.models import Q
from .models import FixedRelation
from apps.genealogy.models import Person,PersonRelation


from typing import List, Dict, Optional, Tuple
from django.db.models import Q
from apps.genealogy.models import Person, PersonRelation

class RelationAutomationEngine:
    """Main engine for automated relation calculation from click paths."""
    
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
        'stepfather': 'STEP_FATHER',
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
    
    @classmethod
    def calculate_relation_from_path(
        cls,
        from_person: Person,
        path_elements: List[str],
        to_person: Optional[Person] = None,
        context: Dict = None
    ) -> Dict:
        """Calculate relation from click path with multi-level support."""
        if not path_elements:
            return {'relation_code': 'SELF', 'label': 'Self'}
        
        # Step 1: Normalize and compose with multi-level support
        current_code = None
        normalized_path = []
        composition_history = []
        
        for i, element in enumerate(path_elements):
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
                # If current_code ends with _BROTHER or _SISTER, it might be UNCLE/AUNT
                if element_code in ['SON', 'DAUGHTER']:
                    if current_code.startswith(('FATHER_', 'MOTHER_', 'UNCLE', 'AUNT')):
                        if element_code == 'SON':
                            current_code = 'COUSIN_MALE'
                        else:
                            current_code = 'COUSIN_FEMALE'
                    else:
                        # Generic composition
                        current_code = f"{current_code}_{element_code}"
                else:
                    # Generic fallback composition
                    current_code = f"{current_code}_{element_code}"
        
        # Step 2: Apply Tamil refinements
        refined_code = cls._apply_refinements(
            base_code=current_code,
            path_elements=normalized_path,
            from_person=from_person,
            to_person=to_person,
            context=context or {}
        )
        
        # Step 3: Get localized label
        label_service = RelationLabelService()
        language = context.get('language', 'ta') if context else 'ta'
        
        label_info = label_service.get_relation_label(
            relation_code=refined_code,
            language=language,
            religion=context.get('religion', '') if context else '',
            caste=context.get('caste', '') if context else '',
            family_name=context.get('family_name', '') if context else ''
        )
        
        return {
            'base_relation': current_code,
            'refined_relation': refined_code,
            'label': label_info['label'],
            'localization_level': label_info['level'],
            'path_used': path_elements,
            'normalized_path': normalized_path,
            'composition_history': composition_history
        }
    
    @classmethod
    def _normalize_relation_input(cls, input_str: str) -> str:
        """Convert inputs to standardized relation codes."""
        # First check extended aliases
        if isinstance(input_str, str):
            key = input_str.lower().replace(' ', '').replace('-', '').replace('_', '')
            if key in cls.RELATION_ALIASES:
                return cls.RELATION_ALIASES[key]
        
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
        }
        
        if isinstance(input_str, str):
            key = input_str.lower().replace(' ', '')
            if key in mapping:
                return mapping[key]
        
        # Default: uppercase or return as is
        return input_str.upper() if isinstance(input_str, str) else str(input_str)
    
    @classmethod
    def _apply_refinements(
        cls,
        base_code: str,
        path_elements: List[str],
        from_person: Person,
        to_person: Optional[Person] = None,
        context: Dict = None
    ) -> str:
        """Apply Tamil-specific refinements with age comparison."""
        
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
            # Father's wife
            if len(path_elements) == 2 and path_elements[0] == 'FATHER':
                return 'STEP_MOTHER'
        
        elif base_code == 'STEP_FATHER':
            # Mother's husband
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
    
    @classmethod
    def _get_age_context(cls, from_person: Person, to_person: Optional[Person] = None) -> Optional[str]:
        """Determine age context between two persons."""
        if not to_person:
            return None
            
        try:
            if hasattr(from_person, 'date_of_birth') and hasattr(to_person, 'date_of_birth'):
                if from_person.date_of_birth and to_person.date_of_birth:
                    if from_person.date_of_birth < to_person.date_of_birth:
                        return 'ELDER'  # from_person is elder
                    elif from_person.date_of_birth > to_person.date_of_birth:
                        return 'YOUNGER'  # from_person is younger
        except (AttributeError, TypeError):
            pass
        
        return None
    
    @classmethod
    def generate_relation_examples(cls) -> List[Dict]:
        """Generate comprehensive examples for testing."""
        return [
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