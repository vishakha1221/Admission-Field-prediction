import requests
import json

url = 'http://127.0.0.1:5000/api/search-institutes'
params = {
    'branch': 'Computer Science Engineering',
    'city': 'Ahmedabad'
}

try:
    resp = requests.get(url, params=params, timeout=5)
    data = resp.json()
    print(f'Status: {resp.status_code}')
    print(f'Results count: {len(data.get("results", []))}')
    print('\nResults:')
    for i, r in enumerate(data.get('results', [])):
        print(f'{i+1}. {r.get("institute_name")} - {r.get("course_name")} - {r.get("college_type")}')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    print('Is the server running on http://127.0.0.1:5000?')
