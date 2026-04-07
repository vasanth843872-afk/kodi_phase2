# apps/genealogy/constants.py

PRIMARY_RELATION_CODES = [
    'MOTHER', 'FATHER',
    'ELDER_BROTHER', 'YOUNGER_BROTHER',
    'ELDER_SISTER', 'YOUNGER_SISTER',
    'BROTHER', 'SISTER',
    'SON', 'DAUGHTER',
    'HUSBAND', 'WIFE',
    'PARENT', 'CHILD',
]

# Optional: separate list for Ashramam if you want to be strict
ASHRAMAM_CODES = [
    'THATHA', 'PAATI', 'PERIYAPPA', 'CHITHAPPA', 'PERIYAMMA', 'CHITHI',
    'MAMA', 'ATHAI', 'ANNA', 'AKKA', 'THAMBI', 'THANGAI',
    'MAGAN', 'MAGHAZH', 'PERAN', 'PETTHI', 'ATHAN', 'ANNI',
    'MARUMAGAN', 'MARUMAGAL', 'MAITHUNAR', 'MAITHUNI',
    'KOLUNTHANAR', 'KOLUNTHIYAZH'
]

PRIMARY_GROUP_CODE = 'PRIMARY'
PRIMARY_GROUP_LABEL_EN = 'Primary Relations'
PRIMARY_GROUP_LABEL_TA = 'முதன்மை உறவுகள்'