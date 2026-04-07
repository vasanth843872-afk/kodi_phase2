# Custom Relative Addition API Documentation

## Overview
This API allows users to add custom relatives with bidirectional relationship labels using 4 simple required fields.

## Endpoint
```
POST /api/persons/{person_id}/add-custom-relative/
```

## Required Fields
| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `from_relationship_name` | string | How the new person relates to the current user (inverse perspective) | "Great Grandson" |
| `to_relationship_name` | string | How the current user relates to the new person (forward perspective) | "Great Grandfather" |
| `name` | string | Full name of the person being added | "Ramasamy" |
| `gender` | string | Gender of the person being added (M, F, or O) | "M" |

## Request Example
```json
{
  "from_relationship_name": "Great Grandson",
  "to_relationship_name": "Great Grandfather", 
  "name": "Ramasamy",
  "gender": "M"
}
```

## Success Response
```json
{
  "success": true,
  "message": "Added Ramasamy as Great Grandfather of Vino",
  "labels": {
    "from_label": "Great Grandson",
    "to_label": "Great Grandfather",
    "combined_label_en": "Great Grandson-Great Grandfather",
    "combined_label_ta": "பெரிய பேரன்-பெரிய தாத்தா"
  },
  "perspectives": {
    "your_view": {
      "relation": "Great Grandfather",
      "label": "Great Grandfather"
    },
    "their_view": {
      "relation": "Great Grandson", 
      "label": "Great Grandson"
    }
  },
  "new_person": {
    "id": 901,
    "full_name": "Ramasamy",
    "gender": "M",
    "is_placeholder": true
  },
  "relation": {
    "id": 456,
    "code": "CUSTOM_GREAT_GRANDFATHER",
    "from_label": "Great Grandson",
    "to_label": "Great Grandfather",
    "combined_label": "Great Grandson-Great Grandfather",
    "status": "confirmed"
  },
  "next_actions": [
    {
      "action": "view_ashramam",
      "label": "View All Ashramam Relations",
      "url": "/api/persons/883/ashramam-relations/"
    },
    {
      "action": "edit_name",
      "label": "Edit Ramasamy's Name",
      "url": "/api/persons/901/update_name/"
    }
  ]
}
```

## Error Responses

### Missing Required Field
```json
{
  "error": "from_relationship_name is required (how the new person relates to you)",
  "code": "missing_from_relationship_name"
}
```

### Invalid Gender
```json
{
  "error": "gender is required and must be M, F, or O",
  "code": "invalid_gender"
}
```

### Duplicate Exclusive Relation
```json
{
  "error": "Vino already has a father",
  "code": "duplicate_relation"
}
```

### Gender Incompatibility
```json
{
  "error": "Father must be male",
  "code": "gender_incompatible"
}
```

## Features

### ✅ Bidirectional Labels
- Stores both perspectives of the relationship
- Labels are saved in `RelationProfileOverride` with full context
- Used in ashramam relations display

### ✅ Smart Category Detection
- Automatically categorizes relations: PARENT, CHILD, SPOUSE, SIBLING, GRANDPARENT, GRANDCHILD, OTHER
- Determines relation direction: ancestor, descendant, same_generation

### ✅ Unique Relation Codes
- Generates `CUSTOM_` prefixed codes from `to_relationship_name`
- Example: "Great Grandfather" → `CUSTOM_GREAT_GRANDFATHER`

### ✅ Tamil Translation Support
- Built-in translations for common relationship terms
- Combined labels available in both English and Tamil

### ✅ Validation
- Required field validation
- Gender validation (M, F, O only)
- Duplicate exclusive relation checks (father, mother, spouse)
- Gender compatibility for relation types

### ✅ Person Creation
- Creates new person with `is_placeholder = True`
- Assigns same family as current person
- Sets appropriate relation status (confirmed/pending)

## Implementation Details

### Database Changes
- Added `is_custom` field to `FixedRelation` model
- Migration: `0006_add_is_custom_to_fixedrelation.py`

### Helper Methods
- `_generate_custom_relation_code()` - Creates unique relation codes
- `_determine_category()` - Maps to relation categories
- `_determine_relation_direction()` - Ancestor/descendant detection
- `_translate_to_tamil()` - Tamil translations
- `_validate_exclusive_relations()` - Prevents duplicates
- `_validate_gender_compatibility()` - Gender validation
- `_create_bidirectional_labels()` - Stores both perspectives
- `_get_bidirectional_labels()` - Retrieves stored labels

### Updated Methods
- `_format_ashramam_relations()` - Now uses stored bidirectional labels for custom relations

## Usage Examples

### Adding a Grandfather
```json
{
  "from_relationship_name": "Grandson",
  "to_relationship_name": "Grandfather",
  "name": "Rajendra",
  "gender": "M"
}
```

### Adding an Aunt
```json
{
  "from_relationship_name": "Niece/Nephew", 
  "to_relationship_name": "Aunt",
  "name": "Lakshmi",
  "gender": "F"
}
```

### Adding a Spouse
```json
{
  "from_relationship_name": "Husband",
  "to_relationship_name": "Wife", 
  "name": "Priya",
  "gender": "F"
}
```

This API provides a simple yet powerful way to add any type of custom relative relationship with proper bidirectional labeling and validation.
