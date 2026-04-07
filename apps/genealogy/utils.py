from collections import deque
from django.db.models import Q
from apps.genealogy.models import Person, PersonRelation
from apps.relations.services import RelationAutomationEngine, RelationLabelService

def get_inverse_relation_code(relation_code: str, from_gender: str, to_gender: str) -> str:
    """
    Inverse relation mapping (same as PersonViewSet._get_inverse_relation_code).
    Reuse or copy from PersonViewSet.
    """
    INVERSE_MAP = {
        'FATHER': {'M': 'SON', 'F': 'DAUGHTER'},
        'MOTHER': {'M': 'SON', 'F': 'DAUGHTER'},
        'SON': {'M': 'FATHER', 'F': 'MOTHER'},
        'DAUGHTER': {'M': 'FATHER', 'F': 'MOTHER'},
        'HUSBAND': {'F': 'WIFE'},
        'WIFE': {'M': 'HUSBAND'},
        'BROTHER': {'M': 'BROTHER', 'F': 'SISTER'},
        'SISTER': {'M': 'BROTHER', 'F': 'SISTER'},
        'ELDER_BROTHER': {'M': 'YOUNGER_BROTHER', 'F': 'YOUNGER_SISTER'},
        'YOUNGER_BROTHER': {'M': 'ELDER_BROTHER', 'F': 'ELDER_SISTER'},
        'ELDER_SISTER': {'M': 'YOUNGER_BROTHER', 'F': 'YOUNGER_SISTER'},
        'YOUNGER_SISTER': {'M': 'ELDER_BROTHER', 'F': 'ELDER_SISTER'},
        # Ashramam relations
        'THATHA': {'M': 'PERAN', 'F': 'PETTHI'},
        'PAATI': {'M': 'PERAN', 'F': 'PETTHI'},
        'PERAN': {'M': 'THATHA', 'F': 'PAATI'},
        'PETTHI': {'M': 'THATHA', 'F': 'PAATI'},
        'MAMA': {'M': 'MARUMAGAN', 'F': 'MARUMAGAL'},
        'ATHAI': {'M': 'MARUMAGAN', 'F': 'MARUMAGAL'},
        'MARUMAGAN': {'M': 'MAMA', 'F': 'ATHAI'},
        'MARUMAGAL': {'M': 'MAMA', 'F': 'ATHAI'},
        'PERIYAPPA': {'M': 'MAGAN', 'F': 'MAGHAZH'},
        'CHITHAPPA': {'M': 'MAGAN', 'F': 'MAGHAZH'},
        'PERIYAMMA': {'M': 'MAGAN', 'F': 'MAGHAZH'},
        'CHITHI': {'M': 'MAGAN', 'F': 'MAGHAZH'},
        'MAGAN': {'M': 'FATHER', 'F': 'MOTHER'},
        'MAGHAZH': {'M': 'FATHER', 'F': 'MOTHER'},
        'ANNA': {'M': 'THAMBI', 'F': 'THANGAI'},
        'AKKA': {'M': 'THAMBI', 'F': 'THANGAI'},
        'THAMBI': {'M': 'ANNA', 'F': 'AKKA'},
        'THANGAI': {'M': 'ANNA', 'F': 'AKKA'},
        'ATHAN': {'F': 'ANNI'},
        'ANNI': {'M': 'ATHAN'},
        'MAITHUNAR': {'M': 'MAITHUNI', 'F': 'MAITHUNAR'},
        'MAITHUNI': {'M': 'MAITHUNAR', 'F': 'MAITHUNI'},
        'KOLUNTHANAR': {'M': 'KOLUNTHIYAZH', 'F': 'KOLUNTHANAR'},
        'KOLUNTHIYAZH': {'M': 'KOLUNTHANAR', 'F': 'KOLUNTHIYAZH'},
    }
    try:
        if relation_code in INVERSE_MAP:
            gender_map = INVERSE_MAP[relation_code]
            if to_gender in gender_map:
                return gender_map[to_gender]
            elif from_gender in gender_map:
                return gender_map[from_gender]
        return relation_code
    except Exception:
        return relation_code


def find_path_with_steps(start_person, target_person, max_depth=5, invert=True):
    """
    Returns a list of steps, each step: {
        'from': Person,
        'to': Person,
        'relation_code': str,
        'original_code': str  # the stored code (optional)
    }
    If invert=True, relation_code is the forward relation from 'from' to 'to'.
    If invert=False, relation_code is the stored code as it exists in the database
    (which may be the inverse of the forward relation).
    """
    if start_person.id == target_person.id:
        return []

    queue = deque([(start_person.id, [])])   # (current_id, steps)
    visited = {start_person.id: 0}
    person_cache = {start_person.id: start_person}

    while queue:
        current_id, steps = queue.popleft()
        current_depth = len(steps)

        if current_id == target_person.id:
            return steps

        if current_depth >= max_depth:
            continue

        relations = PersonRelation.objects.filter(
            Q(from_person_id=current_id) | Q(to_person_id=current_id),
            status__in=['confirmed', 'pending']
        ).select_related('relation', 'from_person', 'to_person')

        for rel in relations:
            if rel.from_person_id == current_id:
                neighbor = rel.to_person
                stored_code = rel.relation.relation_code
                # Forward direction: code is the stored one
                code = stored_code
            else:
                neighbor = rel.from_person
                stored_code = rel.relation.relation_code
                # Backward direction: if invert, we compute inverse; otherwise keep stored
                if invert:
                    code = get_inverse_relation_code(
                        stored_code,
                        rel.to_person.gender,   # current's gender
                        rel.from_person.gender  # neighbor's gender
                    )
                else:
                    code = stored_code   # keep stored code

            if neighbor.id not in visited or visited[neighbor.id] > current_depth + 1:
                visited[neighbor.id] = current_depth + 1
                step = {
                    'from': person_cache[current_id],
                    'to': neighbor,
                    'relation_code': code,
                    'stored_code': stored_code,
                }
                queue.append((neighbor.id, steps + [step]))
                person_cache[neighbor.id] = neighbor

    return None