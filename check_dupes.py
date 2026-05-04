import pandas as pd
from backend.preprocess import standardize_institute_name, standardize_branch, normalize_text

# Load raw CSV
df = pd.read_csv('data/final_acpc_with_fee_data.csv')

# Apply same transformations as backend
df['institute_name'] = df['institute_name'].fillna('').astype(str).map(standardize_institute_name)
df['course_name'] = df['course_name'].fillna('').astype(str).map(standardize_branch)
df['institute_key'] = df['institute_name'].map(normalize_text)

# Filter for Information Technology
it_data = df[df['course_name'].str.strip() == 'Information Technology'].copy()
print(f'Total Information Technology records: {len(it_data)}')

# Check how many times each institute-course appears
dupe_check = it_data.groupby(['institute_key', 'course_name']).size().sort_values(ascending=False)
print(f'\nInstitute-Course combinations appearing multiple times:')
print(dupe_check[dupe_check > 1].head(10))

# Show specific college
gec_gandhi = it_data[it_data['institute_name'].str.contains('Government Engineering College', na=False) & it_data['institute_name'].str.contains('Gandhinagar', na=False)]
print(f'\nGovernment Engineering College, Sector 28 Gandhinagar - Information Technology records: {len(gec_gandhi)}')
print('Years:', gec_gandhi['academic_year'].unique())
