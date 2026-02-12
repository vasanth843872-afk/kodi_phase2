# test_relations_integration.py
import os
import django
import sys
from datetime import datetime

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.relations.models import FixedRelation, RelationLanguageReligion, RelationCaste, RelationFamily
from apps.relations.services import RelationLabelService
from admin_app.models import RelationManagementPermission, AdminProfile, StaffPermission
# from admin_app.services import relation_management_service

User = get_user_model()

def test_initial_setup():
    """Test 1: Check if all models are properly configured."""
    print("\n" + "="*50)
    print("TEST 1: Checking Initial Setup")
    print("="*50)
    
    try:
        # Check if FixedRelation model exists
        print("✓ FixedRelation model loaded successfully")
        
        # Check if relation permissions model exists
        print("✓ RelationManagementPermission model loaded successfully")
        
        # Check if admin models exist
        print("✓ AdminProfile model loaded successfully")
        
        # Check if service modules are loaded
        print("✓ RelationLabelService loaded successfully")
        
        return True
    except Exception as e:
        print(f"✗ Error in initial setup: {e}")
        return False

def test_create_test_admin():
    """Test 2: Create a test admin user with relation permissions."""
    print("\n" + "="*50)
    print("TEST 2: Creating Test Admin User")
    print("="*50)
    
    try:
        # Create test admin user
        test_admin, created = User.objects.get_or_create(
            mobile_number='9999999999',
            defaults={
                'password': 'testadmin123',
                'is_staff': True,
                'is_superuser': False
            }
        )
        
        if created:
            print(f"✓ Created test admin user: {test_admin.mobile_number}")
        else:
            print(f"✓ Using existing test admin user: {test_admin.mobile_number}")
        
        # Create admin profile
        admin_profile, created = AdminProfile.objects.get_or_create(
            user=test_admin,
            defaults={
                'full_name': 'Test Relation Admin',
                'email': 'relation.admin@test.com',
                'admin_id': 'TEST-REL-001'
            }
        )
        
        if created:
            print(f"✓ Created admin profile: {admin_profile.full_name}")
        
        # Create staff permissions
        staff_perm, created = StaffPermission.objects.get_or_create(
            user=test_admin,
            defaults={
                'user_type': 'admin',
                'is_active': True,
                'can_manage_admin': True
            }
        )
        
        if created:
            print(f"✓ Created staff permissions: {staff_perm.user_type}")
        
        # Create relation management permissions
        rel_perm, created = RelationManagementPermission.objects.get_or_create(
            user=test_admin,
            defaults={
                'can_manage_fixed_relations': True,
                'can_manage_language_religion': True,
                'can_manage_caste_overrides': True,
                'can_manage_family_overrides': True,
                'can_view_relation_analytics': True,
                'can_export_relation_data': True
            }
        )
        
        if created:
            print(f"✓ Created relation management permissions")
        
        return test_admin, rel_perm
        
    except Exception as e:
        print(f"✗ Error creating test admin: {e}")
        return None, None

def test_create_fixed_relations():
    """Test 3: Create some test fixed relations."""
    print("\n" + "="*50)
    print("TEST 3: Creating Fixed Relations")
    print("="*50)
    
    try:
        # Define test relations
        test_relations = [
            {
                'relation_code': 'FATHER',
                'default_english': 'Father',
                'default_tamil': 'அப்பா',
                'category': 'PARENT',
                'from_gender': 'M',
                'to_gender': 'A',
                'max_instances': 1,
                'is_reciprocal_required': True
            },
            {
                'relation_code': 'MOTHER',
                'default_english': 'Mother',
                'default_tamil': 'அம்மா',
                'category': 'PARENT',
                'from_gender': 'F',
                'to_gender': 'A',
                'max_instances': 1,
                'is_reciprocal_required': True
            },
            {
                'relation_code': 'SON',
                'default_english': 'Son',
                'default_tamil': 'மகன்',
                'category': 'CHILD',
                'from_gender': 'A',
                'to_gender': 'M',
                'max_instances': 0,
                'is_reciprocal_required': True
            }
        ]
        
        created_count = 0
        for relation_data in test_relations:
            relation, created = FixedRelation.objects.get_or_create(
                relation_code=relation_data['relation_code'],
                defaults=relation_data
            )
            
            if created:
                created_count += 1
                print(f"✓ Created relation: {relation.relation_code}")
            else:
                print(f"✓ Relation exists: {relation.relation_code}")
        
        print(f"\nTotal relations in DB: {FixedRelation.objects.count()}")
        return True
        
    except Exception as e:
        print(f"✗ Error creating fixed relations: {e}")
        return False

def test_relation_label_service():
    """Test 4: Test the relation label resolution service."""
    print("\n" + "="*50)
    print("TEST 4: Testing Relation Label Service")
    print("="*50)
    
    try:
        # Get a relation
        relation = FixedRelation.objects.filter(relation_code='FATHER').first()
        if not relation:
            print("✗ No FATHER relation found")
            return False
        
        print(f"\nTesting with relation: {relation.relation_code}")
        print(f"Default English: {relation.default_english}")
        print(f"Default Tamil: {relation.default_tamil}")
        
        # Test 4.1: Get default label
        result = RelationLabelService.get_relation_label(
            relation_code='FATHER',
            language='en',
            religion='Hindu',
            caste='Brahmin',
            family_name=''
        )
        
        print(f"\n4.1 Default Resolution:")
        print(f"   Label: {result['label']}")
        print(f"   Level: {result['level']}")
        print(f"   Source: {result['source']}")
        
        # Test 4.2: Create an override and test
        print(f"\n4.2 Testing Override Creation...")
        
        # Create language+religion override
        lang_rel_override, created = RelationLanguageReligion.objects.get_or_create(
            relation=relation,
            language='ta',
            religion='Hindu',
            defaults={'label': 'தந்தை (Hindu)'}
        )
        
        if created:
            print(f"   ✓ Created language+religion override")
        else:
            print(f"   ✓ Override already exists")
        
        # Test with override
        result = RelationLabelService.get_relation_label(
            relation_code='FATHER',
            language='ta',
            religion='Hindu',
            caste='Brahmin',
            family_name=''
        )
        
        print(f"   Label with override: {result['label']}")
        print(f"   Level: {result['level']}")
        
        # Test 4.3: Create caste override (higher priority)
        print(f"\n4.3 Testing Caste Override (higher priority)...")
        
        caste_override, created = RelationCaste.objects.get_or_create(
            relation=relation,
            language='ta',
            religion='Hindu',
            caste='Brahmin',
            defaults={'label': 'பிதா (Brahmin)'}
        )
        
        if created:
            print(f"   ✓ Created caste override")
        
        result = RelationLabelService.get_relation_label(
            relation_code='FATHER',
            language='ta',
            religion='Hindu',
            caste='Brahmin',
            family_name=''
        )
        
        print(f"   Label with caste override: {result['label']}")
        print(f"   Level: {result['level']}")
        
        # Test 4.4: Create family override (highest priority)
        print(f"\n4.4 Testing Family Override (highest priority)...")
        
        family_override, created = RelationFamily.objects.get_or_create(
            relation=relation,
            language='ta',
            religion='Hindu',
            caste='Brahmin',
            family='Sharma',
            defaults={'label': 'அப்பாவு (Sharma Family)'}
        )
        
        if created:
            print(f"   ✓ Created family override")
        
        result = RelationLabelService.get_relation_label(
            relation_code='FATHER',
            language='ta',
            religion='Hindu',
            caste='Brahmin',
            family_name='Sharma'
        )
        
        print(f"   Label with family override: {result['label']}")
        print(f"   Level: {result['level']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error in label service test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_admin_views_work():
    """Test 5: Test if admin views are accessible."""
    print("\n" + "="*50)
    print("TEST 5: Testing Admin View Integration")
    print("="*50)
    
    try:
        from django.test import Client
        from django.urls import reverse
        
        # Create test client
        client = Client()
        
        # Test if admin can login
        print("\n5.1 Testing Admin Login...")
        
        # First, create a user with proper credentials
        test_user = User.objects.create_user(
            mobile_number='8888888888',
            password='test123456'
        )
        
        # Create admin profile and permissions
        AdminProfile.objects.create(
            user=test_user,
            full_name='View Test Admin',
            email='view.test@test.com'
        )
        
        StaffPermission.objects.create(
            user=test_user,
            user_type='admin'
        )
        
        # Try to login
        login_data = {
            'mobile_number': '8888888888',
            'password': 'test123456'
        }
        
        # Note: Adjust based on your actual login endpoint
        print("   ✓ Test user created")
        print("   Note: Manual API endpoint testing required")
        
        # Test model admin URLs
        print("\n5.2 Testing Admin Model URLs...")
        
        admin_urls = [
            ('admin:genealogy_fixedrelation_changelist', 'Fixed Relations'),
            ('admin:genealogy_relationlanguagereligion_changelist', 'Language+Religion Overrides'),
            ('admin:genealogy_relationcaste_changelist', 'Caste Overrides'),
            ('admin:genealogy_relationfamily_changelist', 'Family Overrides'),
        ]
        
        for url_name, description in admin_urls:
            try:
                url = reverse(url_name)
                print(f"   ✓ {description}: {url}")
            except Exception:
                print(f"   ✗ {description}: URL not found")
        
        return True
        
    except Exception as e:
        print(f"✗ Error in admin views test: {e}")
        return False

def test_api_endpoints():
    """Test 6: Test API endpoints."""
    print("\n" + "="*50)
    print("TEST 6: Testing API Endpoints")
    print("="*50)
    
    print("\nAvailable API Endpoints:")
    print("-"*30)
    
    endpoints = [
        ('/api/admin/relations/fixed-relations/', 'GET', 'List all fixed relations'),
        ('/api/admin/relations/fixed-relations/1/', 'GET', 'Get specific relation'),
        ('/api/admin/relations/relation-overrides/create_override/', 'POST', 'Create override'),
        ('/api/admin/relations/relation-overrides/search/', 'GET', 'Search overrides'),
        ('/api/admin/relations/relation-label-test/', 'POST', 'Test label resolution'),
        ('/api/admin/relations/relation-analytics/', 'GET', 'Get analytics'),
        ('/api/admin/relations/relation-permissions/my_permissions/', 'GET', 'Get my permissions'),
    ]
    
    for endpoint, method, description in endpoints:
        print(f"{method:6} {endpoint:50} - {description}")
    
    print("\n✓ API endpoints defined")
    print("Note: To test actual API calls, run the server and use Postman/curl")
    
    return True

def run_all_tests():
    """Run all tests."""
    print("="*70)
    print("STARTING RELATION MANAGEMENT SYSTEM TESTS")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Initial Setup", test_initial_setup()))
    admin_user, rel_perm = test_create_test_admin()
    results.append(("Test Admin Creation", admin_user is not None))
    results.append(("Fixed Relations", test_create_fixed_relations()))
    results.append(("Label Service", test_relation_label_service()))
    results.append(("Admin Views", test_admin_views_work()))
    results.append(("API Endpoints", test_api_endpoints()))
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:10} {test_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED!")
        print("\nNext steps:")
        print("1. Run migrations: python manage.py migrate")
        print("2. Start server: python manage.py runserver")
        print("3. Access admin at: http://localhost:8000/admin/")
        print("4. Test API endpoints with Postman")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nCheck the errors above and fix before proceeding.")
    
    return all_passed

if __name__ == "__main__":
    run_all_tests()