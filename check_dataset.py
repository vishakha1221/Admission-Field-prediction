import sys
from pathlib import Path
BASE_DIR = Path('.').resolve()
sys.path.insert(0, str(BASE_DIR))
from backend.app import load_fee_recommendation_dataset

# Check what columns are in the fee dataset
df = load_fee_recommendation_dataset()
print("Columns in fee_dataset:")
print(df.columns.tolist())

print("\nFirst few rows with institute_key:")
print(df[['institute_name', 'course_name', 'institute_key', 'college_type']].head(10))

# Check for duplicates
print("\nDuplicate check (before dedup):")
dupes = df[['institute_key', 'course_name']].duplicated(keep=False).sum()
print(f"Rows with duplicates: {dupes}")

# Check specific combination
print("\nAditya Silver Oak occurrences:")
aditya = df[df['institute_name'].str.contains('Aditya Silver Oak', na=False)]
print(aditya[['institute_name', 'course_name', 'institute_key']].to_string())
