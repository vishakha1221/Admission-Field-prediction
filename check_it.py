import pandas as pd
from backend.preprocess import standardize_branch, standardize_institute_name, normalize_text

df = pd.read_csv('data/final_acpc_with_fee_data.csv')
df['course_name'] = df['course_name'].fillna('').astype(str).map(standardize_branch)
df['institute_name'] = df['institute_name'].fillna('').astype(str).map(standardize_institute_name)
df['institute_key'] = df['institute_name'].map(normalize_text)

# Filter for Information Technology only
it = df[df['course_name'] == 'Information Technology'].copy()
print(f'Total IT records in raw data: {len(it)}')

# Deduplicate like the backend does
it_dedup = it.drop_duplicates(subset=['institute_key', 'course_name'], keep='first')
print(f'After dedup: {len(it_dedup)} unique colleges')

# Just get Govt colleges
it_govt = it_dedup[it_dedup['college_type'] == 'Govt']
print(f'\nGovt colleges offering IT: {len(it_govt)}')
for idx, row in it_govt.head(10).iterrows():
    print(f'  {row["institute_name"]}')
