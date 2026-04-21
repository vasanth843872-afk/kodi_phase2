#!/usr/bin/env python
"""
Analyze unused functions and logic in KODI3 project
"""
import os
import sys
import ast
import re
from collections import defaultdict

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kodi_core.settings')
import django
from django.conf import settings
django.setup()

def analyze_file(file_path, app_name):
    """Analyze a Python file for unused functions."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Find all function definitions
        functions = []
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        
        # Find function calls
        function_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    function_calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    function_calls.add(node.func.attr)
        
        return {
            'file': file_path,
            'functions': functions,
            'classes': classes,
            'function_calls': list(function_calls),
            'total_functions': len(functions)
        }
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return None

def find_unused_functions():
    """Find potentially unused functions across the project."""
    apps_dir = os.path.join(os.path.dirname(__file__), 'apps')
    
    all_functions = defaultdict(list)
    all_calls = defaultdict(set)
    
    # Analyze all Python files in apps
    for app_name in os.listdir(apps_dir):
        app_path = os.path.join(apps_dir, app_name)
        if os.path.isdir(app_path):
            for root, dirs, files in os.walk(app_path):
                for file in files:
                    if file.endswith('.py') and not file.startswith('__'):
                        file_path = os.path.join(root, file)
                        analysis = analyze_file(file_path, app_name)
                        if analysis:
                            for func in analysis['functions']:
                                all_functions[app_name].append({
                                    'function': func,
                                    'file': file_path
                                })
                            for call in analysis['function_calls']:
                                all_calls[app_name].add(call)
    
    # Find unused functions
    unused_functions = defaultdict(list)
    
    for app_name, functions in all_functions.items():
        calls = all_calls[app_name]
        for func_info in functions:
            func_name = func_info['function']
            
            # Skip common patterns
            if (func_name.startswith('_') or 
                func_name in ['main', 'run', 'handle', 'get', 'post', 'put', 'delete'] or
                func_name.startswith('test_')):
                continue
            
            # Check if function is called
            is_called = any(
                func_name in call or 
                func_name.endswith(call) or 
                call.endswith(func_name)
                for call in calls
            )
            
            # Check if it's a Django view or model method
            file_path = func_info['file']
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Skip if it's a Django special method
            if re.search(r'@.*method|@.*property|@.*class_method', content):
                continue
            
            if not is_called:
                unused_functions[app_name].append({
                    'function': func_name,
                    'file': file_path,
                    'lines': _find_function_lines(content, func_name)
                })
    
    return unused_functions

def _find_function_lines(content, func_name):
    """Find line numbers where function is defined."""
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if f'def {func_name}(' in line or f'def {func_name}(' in line:
            return i
    return 0

def analyze_urls():
    """Analyze URL patterns for unused endpoints."""
    urls_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file == 'urls.py':
                urls_files.append(os.path.join(root, file))
    
    unused_patterns = []
    
    for urls_file in urls_files:
        try:
            with open(urls_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find URL patterns
            patterns = re.findall(r'path\([\'"]([^\'"]+)[\'"]', content)
            
            # Check if patterns are referenced
            for pattern in patterns:
                if pattern in ['admin/', 'api/', 'static/']:
                    continue  # Core patterns
                
                # Simple check - could be improved
                if pattern not in content.replace(f"path('{pattern}'", ''):
                    unused_patterns.append({
                        'pattern': pattern,
                        'file': urls_file
                    })
        except Exception as e:
            print(f"Error analyzing {urls_file}: {e}")
    
    return unused_patterns

def main():
    print("🔍 ANALYZING UNUSED CODE IN KODI3 PROJECT")
    print("=" * 60)
    
    # Find unused functions
    unused_functions = find_unused_functions()
    
    print("\n📝 UNUSED FUNCTIONS:")
    print("-" * 40)
    
    total_unused = 0
    for app_name, functions in unused_functions.items():
        if functions:
            print(f"\n📁 App: {app_name}")
            for func in functions[:5]:  # Limit to 5 per app
                rel_path = os.path.relpath(func['file'], '.')
                print(f"  ❌ {func['function']}() - {rel_path}:{func['lines']}")
                total_unused += 1
            if len(functions) > 5:
                print(f"  ... and {len(functions) - 5} more")
    
    # Analyze URLs
    unused_patterns = analyze_urls()
    
    print(f"\n🌐 UNUSED URL PATTERNS:")
    print("-" * 40)
    
    for pattern in unused_patterns[:10]:  # Limit to 10
        rel_path = os.path.relpath(pattern['file'], '.')
        print(f"  ❌ {pattern['pattern']} - {rel_path}")
    
    print(f"\n📊 SUMMARY:")
    print("-" * 40)
    print(f"Total unused functions: {total_unused}")
    print(f"Total unused URL patterns: {len(unused_patterns)}")
    
    if total_unused == 0 and len(unused_patterns) == 0:
        print("✅ No obvious unused code found!")
    else:
        print(f"⚠️  Found {total_unused} potentially unused functions")
        print("💡 Consider reviewing and removing unused code")

if __name__ == '__main__':
    main()
