from pathlib import Path

import joblib
import pandas as pd

from backend.preprocess import (
    encode_training_data,
    load_prediction_dataset,
    standardize_category,
    standardize_quota,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "acpc_admission_data.csv"


def _resolve_model_file():
    """Find the trained model in common project locations."""
    candidate_files = [
        BASE_DIR / "model" / "model.pkl",
        BASE_DIR / "model" / "trained_model.pkl",
        BASE_DIR / "models" / "model.pkl",
        BASE_DIR / "models" / "trained_model.pkl",
        BASE_DIR / "idel" / "model.pkl",
        BASE_DIR / "idel" / "trained_model.pkl",
    ]

    for candidate in candidate_files:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No model file found in model/, models/, or idel/")


def load_model_bundle():
    """Load the model and rebuild encoders from the CSV."""
    model_file = _resolve_model_file()
    model_artifact = joblib.load(model_file)

    if isinstance(model_artifact, dict) and "model" in model_artifact:
        model = model_artifact["model"]
        category_encoder = model_artifact.get("category_encoder")
        quota_encoder = model_artifact.get("quota_encoder")
        target_encoder = model_artifact.get("target_encoder")
    else:
        model = model_artifact
        category_encoder = None
        quota_encoder = None
        target_encoder = None

    dataset = load_prediction_dataset()
    if category_encoder is None or quota_encoder is None or target_encoder is None:
        encoded_data, category_encoder, quota_encoder, target_encoder = encode_training_data(dataset)
    else:
        encoded_data, _, _, _ = encode_training_data(dataset)

    return model, category_encoder, quota_encoder, target_encoder, encoded_data


def check_prediction(rank, category, quota, actual_admission_field):
    """Print the prediction result and whether it matches the actual field."""
    model, category_encoder, quota_encoder, target_encoder, _ = load_model_bundle()

    category = standardize_category(category)
    quota = standardize_quota(quota)
    category_encoded = category_encoder.transform([category])[0]
    quota_encoded = quota_encoder.transform([quota])[0]

    prediction_features = pd.DataFrame(
        [[rank, category_encoded, quota_encoded]],
        columns=["rank", "category", "quota"],
    )
    predicted_encoded = model.predict(prediction_features)[0]
    predicted_field = target_encoder.inverse_transform([predicted_encoded])[0]

    is_correct = str(predicted_field).strip().lower() == str(actual_admission_field).strip().lower()

    print("Input values:")
    print(f"  rank: {rank}")
    print(f"  category: {category}")
    print(f"  quota: {quota}")
    print(f"  actual admission field: {actual_admission_field}")
    print()
    print(f"Predicted field: {predicted_field}")
    print(f"Matched: {'Yes' if is_correct else 'No'}")


def run_sample_from_csv(row_index=0):
    """Check one known row from the CSV against the trained model."""
    data = pd.read_csv(DATA_FILE)
    sample = data.iloc[row_index]

    check_prediction(
        rank=int(sample["rank"]),
        category=str(sample["category"]),
        quota=str(sample["quota"]),
        actual_admission_field=str(sample["admission_field"]),
    )


if __name__ == "__main__":
    # Change the row index if you want to test another known record from the CSV.
    run_sample_from_csv(row_index=12)