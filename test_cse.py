import sys
from pathlib import Path
BASE_DIR = Path('.').resolve()
sys.path.insert(0, str(BASE_DIR))
from backend.app import app

with app.test_client() as client:
    # Test with branch=Computer Science Engineering
    print('=== Search: Branch=Computer Science Engineering, City=Ahmedabad ===')
    resp = client.get('/api/search-institutes?branch=Computer%20Science%20Engineering&city=Ahmedabad')
    data = resp.get_json()
    print(f'Results: {len(data.get("results", []))}')
    
    for i, r in enumerate(data.get('results', [])[:10]):
        print(f'{i+1}. {r.get("institute_name")[:50]} - {r.get("college_type")}')
    
    # Check for duplicates
    print(f'\nChecking for duplicates:')
    seen = set()
    dupes = []
    for row in data.get('results', []):
        key = (row.get('institute_name'), row.get('course_name'))
        if key in seen:
            dupes.append(key)
        seen.add(key)
    
    print(f'Unique institute-branch combinations: {len(seen)}')
    print(f'Duplicate combinations found: {len(dupes)}')
    if dupes:
        print(f'Duplicates: {dupes}')
