# apps/genealogy/category_definitions.py

CATEGORIES = {
    'maternal': {
        'code': 'MATERNAL_LINE',
        'default_label_ta': 'தாய்வழி',
        'default_label_en': 'Maternal Line',
        'lineage_edges': ['MOTHER'],          # follow these edges to determine lineage
        'direction': 'both',
    },
    'paternal': {
        'code': 'PATERNAL_LINE',
        'default_label_ta': 'தந்தைவழி',
        'default_label_en': 'Paternal Line',
        'lineage_edges': ['FATHER'],
        'direction': 'both',
    },
    # 'leader_line': {
    #     'code': 'LEADER_LINE',
    #     'default_label_ta': 'தலைவழி',
    #     'default_label_en': 'Leader Line',
    #     'relation_codes': ['FATHER', 'GRANDFATHER', 'MOTHER', 'GRANDMOTHER'],
    # },
    # 'clan_line': {
    #     'code': 'CLAN_LINE',
    #     'default_label_ta': 'குலவழி',
    #     'default_label_en': 'Clan Line',
    #     # custom logic – will be handled separately
    #     'custom': True,
    # },
    
    'son_line': {
        'code': 'SON_LINE',
        'default_label_ta': 'மகன்வழி',
        'default_label_en': 'Son Line',
        'lineage_edges': ['SON', 'GRANDSON'],
        'direction': 'down',
    },
    'daughter_line': {
        'code': 'DAUGHTER_LINE',
        'default_label_ta': 'மகள்வழி',
        'default_label_en': 'Daughter Line',
        'lineage_edges': ['DAUGHTER', 'GRANDDAUGHTER'],
        'direction': 'down',
    },
    'ashramam': {
        'code': 'ASHRAMAM',
        'default_label_ta': 'ஆஸ்ரமம்',
        'default_label_en': 'Ashramam',
        'relation_codes': ['THATHA', 'PAATI', 'PERIYAPPA', 'CHITHAPPA', 'PERIYAMMA', 'CHITHI',
                                'MAMA', 'ATHAI', 'ANNA', 'AKKA', 'THAMBI', 'THANGAI',
                                'MAGAN', 'MAGHAZH', 'PERAN', 'PETTHI', 'ATHAN', 'ANNI',
                                'MARUMAGAN', 'MARUMAGAL', 'MAITHUNAR', 'MAITHUNI',
                                'KOLUNTHANAR', 'KOLUNTHIYAZH'],
    },
    'elder_brother_line': {
        'code': 'ELDER_BROTHER_LINE',
        'default_label_ta': 'அண்ணன்வழி',
        'default_label_en': 'Elder Brother Line',
        'lineage_edges': ['ELDER_BROTHER'],
        'direction': 'both',  
    },
    'younger_brother_line': {
        'code': 'YOUNGER_BROTHER_LINE',
        'default_label_ta': 'தம்பிவழி',
        'default_label_en': 'Younger Brother Line',
        'lineage_edges': ['YOUNGER_BROTHER'],
        'direction': 'both',  
    },
    'elder_sister_line': {
        'code': 'ELDER_SISTER_LINE',
        'default_label_ta': 'அக்காவழி',
        'default_label_en': 'Elder Sister Line',
        'lineage_edges': ['ELDER_SISTER',],
        'direction': 'both',  
    },
    'younger_sister_line': {
        'code': 'YOUNGER_SISTER_LINE',
        'default_label_ta': 'தங்கைவழி',
        'default_label_en': 'Younger Sister Line',
        'lineage_edges': ['YOUNGER_SISTER'],
        'direction': 'both'
    },
    'primary_line': {
    'code': 'PRIMARY_LINE',
    'default_label_ta': 'அடிப்படை உறவுகள்',   # choose appropriate Tamil
    'default_label_en': 'Primary Relations',
    'relation_codes': [
        'MOTHER', 'FATHER',
        'ELDER_BROTHER', 'YOUNGER_BROTHER', 'ELDER_SISTER', 'YOUNGER_SISTER',
        'SON', 'DAUGHTER',
        'HUSBAND', 'WIFE',
    ],
}
    
}