from pathlib import Path
from functools import lru_cache
from math import ceil
import re
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import joblib
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

from backend.preprocess import (
    INSTITUTE_MASTER_FILE_V2,
    encode_training_data,
    infer_city,
    load_institute_search_dataset,
    load_prediction_dataset,
    normalize_text,
    standardize_branch,
    standardize_institute_name,
    standardize_category,
    standardize_quota,
)


FRONTEND_DIR = BASE_DIR / "frontend"
MODEL_FILE = BASE_DIR / "model" / "model.pkl"
DATA_FILE = BASE_DIR / "data" / "acpc_admission_data.csv"
ENRICHED_DATA_FILE = BASE_DIR / "data" / "acpc_admission_enriched.csv"
FEE_DATA_FILES = [
    BASE_DIR / "data" / "acpc_admission_with_original_fees_data.csv",
    BASE_DIR / "data" / "final_acpc_with_fee_data.csv",
]


PREDICTION_DEFAULTS = {
    "category": "GENERAL",
    "quota": "GUJCET",
}

app = Flask(__name__)


@lru_cache(maxsize=1)
def load_institute_master_dataset():
    """Load and normalize institute master data once for fast filter queries."""
    if not INSTITUTE_MASTER_FILE_V2.exists():
        return None

    institute_master = pd.read_csv(INSTITUTE_MASTER_FILE_V2).copy()
    for column in ["institute_name", "boys_hostel", "girls_hostel", "official_website"]:
        if column not in institute_master.columns:
            institute_master[column] = ""

    institute_master["institute_name"] = (
        institute_master["institute_name"].fillna("").astype(str).map(standardize_institute_name)
    )
    institute_master["boys_hostel"] = institute_master["boys_hostel"].fillna("").astype(str).str.strip()
    institute_master["girls_hostel"] = institute_master["girls_hostel"].fillna("").astype(str).str.strip()
    institute_master["official_website"] = institute_master["official_website"].fillna("").astype(str).str.strip()
    institute_master["city"] = institute_master["institute_name"].map(infer_city)
    institute_master["_dedupe_key"] = institute_master["institute_name"].map(normalize_text)
    institute_master = institute_master[institute_master["_dedupe_key"] != ""].copy()

    institute_master["_has_website"] = institute_master["official_website"].astype(str).str.strip() != ""
    institute_master = institute_master.sort_values(["_dedupe_key", "_has_website"], ascending=[True, False])
    institute_master = institute_master.drop_duplicates(subset=["_dedupe_key"])
    return institute_master


@lru_cache(maxsize=1)
def load_institute_master_lookup():
    """Build fast lookups for city and hostel metadata."""
    institute_master = load_institute_master_dataset()
    if institute_master is None or institute_master.empty:
        return {}

    lookup = {}
    for _, row in institute_master.iterrows():
        lookup[str(row["_dedupe_key"])] = {
            "city": str(row.get("city", "") or "").strip(),
            "boys_hostel": str(row.get("boys_hostel", "") or "").strip(),
            "girls_hostel": str(row.get("girls_hostel", "") or "").strip(),
            "official_website": str(row.get("official_website", "") or "").strip(),
        }

    return lookup


def _extract_fee_amount(value):
    """Extract the first numeric fee amount from the source text."""
    if value is None or pd.isna(value):
        return None

    match = re.search(r"(\d[\d,]*)", str(value))
    if not match:
        return None

    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _academic_year_sort_key(value):
    """Turn an academic year string into a sortable integer key."""
    if value is None or pd.isna(value):
        return 0

    match = re.search(r"(\d{4})", str(value))
    if not match:
        return 0

    try:
        return int(match.group(1))
    except ValueError:
        return 0


@lru_cache(maxsize=1)
def load_fee_recommendation_dataset():
    """Load the fee dataset and enrich it with verified website links."""
    fee_file = next((candidate for candidate in FEE_DATA_FILES if candidate.exists()), None)
    if fee_file is None:
        return pd.DataFrame()

    dataset = pd.read_csv(fee_file).copy()
    required_columns = [
        "institute_name",
        "course_name",
        "category",
        "quota",
        "admission_field",
        "tuition_fee",
        "college_type",
        "district",
        "academic_year",
        "first_rank",
        "last_rank",
    ]
    for column in required_columns:
        if column not in dataset.columns:
            dataset[column] = ""

    dataset["institute_name"] = dataset["institute_name"].fillna("").astype(str).map(standardize_institute_name)
    dataset["course_name"] = dataset["course_name"].fillna("").astype(str).map(standardize_branch)
    dataset["admission_field"] = dataset["admission_field"].fillna("").astype(str).map(standardize_branch)
    dataset["category"] = dataset["category"].fillna("").astype(str).map(standardize_category)
    dataset["quota"] = dataset["quota"].fillna("").astype(str).map(standardize_quota)
    dataset["college_type"] = dataset["college_type"].fillna("").astype(str).str.strip()
    dataset["district"] = dataset["district"].fillna("").astype(str).str.strip()
    dataset["tuition_fee"] = dataset["tuition_fee"].fillna("").astype(str).str.strip()
    dataset["fee_amount"] = dataset["tuition_fee"].map(_extract_fee_amount)
    dataset["rank_floor"] = pd.to_numeric(dataset["first_rank"], errors="coerce")
    dataset["rank_ceiling"] = pd.to_numeric(dataset["last_rank"], errors="coerce")
    dataset["academic_year_sort"] = dataset["academic_year"].map(_academic_year_sort_key)
    dataset["institute_key"] = dataset["institute_name"].map(normalize_text)

    institute_master = load_institute_master_dataset()
    lookup = load_institute_master_lookup()

    dataset["official_website"] = dataset["institute_key"].map(
        lambda key: lookup.get(str(key), {}).get("official_website", "")
    ).fillna("").astype(str).str.strip()
    dataset["city"] = dataset["institute_key"].map(lambda key: lookup.get(str(key), {}).get("city", "")).fillna("").astype(str).str.strip()
    dataset["boys_hostel"] = dataset["institute_key"].map(lambda key: lookup.get(str(key), {}).get("boys_hostel", "")).fillna("").astype(str).str.strip()
    dataset["girls_hostel"] = dataset["institute_key"].map(lambda key: lookup.get(str(key), {}).get("girls_hostel", "")).fillna("").astype(str).str.strip()
    dataset = dataset[
        (dataset["institute_name"].astype(str).str.strip() != "")
        & (dataset["course_name"].astype(str).str.strip() != "")
        & (dataset["admission_field"].astype(str).str.strip() != "")
        & (dataset["category"].astype(str).str.strip() != "")
        & (dataset["quota"].astype(str).str.strip() != "")
        & (dataset["college_type"].astype(str).str.strip() != "")
        & (dataset["district"].astype(str).str.strip() != "")
        & dataset["fee_amount"].notna()
    ].copy()

    dataset = dataset.sort_values(
        ["academic_year_sort", "fee_amount", "rank_ceiling", "rank_floor", "institute_name"],
        ascending=[False, True, True, True, True],
    )
    # Remove duplicates: keep one row per college-branch combination (ignore category/quota)
    dataset = dataset.drop_duplicates(
        subset=["institute_key", "course_name"],
        keep="first",
    )
    return dataset


def _normalize_college_type(value):
    """Normalize college type filters to source values."""
    if value is None:
        return ""

    text = str(value).strip()
    if text.casefold() == "none":
        return ""

    return text


def _json_safe_value(value):
    """Convert pandas/NumPy missing values to None for JSON serialization."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _json_safe_records(dataframe):
    """Convert a dataframe into JSON-safe record dictionaries."""
    records = dataframe.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            record[key] = _json_safe_value(value)
    return records


def _parse_optional_int(value):
    """Convert a numeric form value to an int if possible."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _recommend_eligible_institutes(rank, category, quota, predicted_field, fee_min=None, fee_max=None, college_type=None, limit=None):
    """Return verified institute rows that match the prediction and optional filters."""
    source_dataset = load_fee_recommendation_dataset().copy()
    if source_dataset.empty:
        return [], False

    selected_category = standardize_category(category or PREDICTION_DEFAULTS["category"])
    selected_quota = standardize_quota(quota or PREDICTION_DEFAULTS["quota"])
    selected_field = standardize_branch(predicted_field)
    selected_college_type = _normalize_college_type(college_type)

    if selected_category:
        source_dataset = source_dataset[source_dataset["category"].astype(str).str.casefold() == selected_category.casefold()]
    if selected_quota:
        source_dataset = source_dataset[source_dataset["quota"].astype(str).str.casefold() == selected_quota.casefold()]
    if selected_college_type:
        source_dataset = source_dataset[source_dataset["college_type"].astype(str).str.casefold() == selected_college_type.casefold()]

    if fee_min is not None:
        source_dataset = source_dataset[source_dataset["fee_amount"] >= fee_min]
    if fee_max is not None:
        source_dataset = source_dataset[source_dataset["fee_amount"] <= fee_max]

    candidate_datasets = []
    if selected_category and selected_quota:
        candidate_datasets.append(
            source_dataset[
                (source_dataset["category"].astype(str).str.casefold() == selected_category.casefold())
                & (source_dataset["quota"].astype(str).str.casefold() == selected_quota.casefold())
            ].copy()
        )
    if selected_category:
        candidate_datasets.append(
            source_dataset[source_dataset["category"].astype(str).str.casefold() == selected_category.casefold()].copy()
        )
    if selected_quota:
        candidate_datasets.append(
            source_dataset[source_dataset["quota"].astype(str).str.casefold() == selected_quota.casefold()].copy()
        )
    candidate_datasets.append(source_dataset.copy())

    windows = [500, 2000, 5000, 20000, 50000]
    dataset = pd.DataFrame()
    selected_window = 0
    for candidate_source in candidate_datasets:
        if candidate_source.empty:
            continue

        lower_rank = candidate_source[["rank_floor", "rank_ceiling"]].min(axis=1)
        upper_rank = candidate_source[["rank_floor", "rank_ceiling"]].max(axis=1)

        for window in windows:
            local = candidate_source[(lower_rank <= (rank + window)) & (upper_rank >= (rank - window))].copy()
            if len(local) >= 4:
                dataset = local
                selected_window = window
                break
        else:
            local = candidate_source[(lower_rank <= (rank + windows[-1])) & (upper_rank >= (rank - windows[-1]))].copy()
            if not local.empty:
                dataset = local
                selected_window = windows[-1]

        if not dataset.empty:
            break

    if dataset.empty:
        return [], False

    matched_predicted_field = False
    if selected_field:
        exact_field_rows = dataset[
            dataset["admission_field"].astype(str).str.casefold() == selected_field.casefold()
        ].copy()
        matched_predicted_field = not exact_field_rows.empty
        if not exact_field_rows.empty:
            dataset = pd.concat([exact_field_rows, dataset], ignore_index=True)
            # After preferring exact field rows, dedupe by institute+branch so we don't repeat the same branch
            dataset = dataset.drop_duplicates(subset=["institute_key", "course_name"], keep="first")

    dataset["rank_gap"] = (
        dataset[["rank_floor", "rank_ceiling"]].max(axis=1) - rank
    ).abs()
    dataset["rank_window"] = selected_window
    dataset = dataset.sort_values(["rank_gap", "fee_amount", "institute_name"], ascending=[True, True, True])

    columns = [
        "institute_name",
        "course_name",
        "admission_field",
        "tuition_fee",
        "fee_amount",
        "college_type",
        "district",
        "city",
        "boys_hostel",
        "girls_hostel",
        "official_website",
        "academic_year",
        "program_type",
        "category",
        "quota",
        "first_rank",
        "last_rank",
        "rank_gap",
        "rank_window",
    ]
    # Return all results if no limit specified, otherwise apply limit
    if limit is not None:
        dataset = dataset[columns].head(max(1, int(limit)))
    else:
        dataset = dataset[columns]
    
    recommendations = _json_safe_records(dataset)
    for row in recommendations:
        row["official_website"] = str(row.get("official_website", "") or "").strip()
    return recommendations, matched_predicted_field


def _build_prediction_response(rank, category, quota, fee_min=None, fee_max=None, college_type=None, include_accuracy=False):
    """Build the API response shared by predict and accuracy endpoints."""
    model_bundle = load_model_bundle()
    if not model_bundle:
        return None, None

    predicted_field = _predict_field(model_bundle, rank, category, quota)
    eligible_institutes, matched_predicted_field = _recommend_eligible_institutes(
        rank=rank,
        category=category,
        quota=quota,
        predicted_field=predicted_field,
        fee_min=fee_min,
        fee_max=fee_max,
        college_type=college_type,
    )

    response = {
        "predicted_field": predicted_field,
        "selected_rank": rank,
        "selected_category": standardize_category(category or model_bundle["default_category"]),
        "selected_quota": standardize_quota(quota or model_bundle["default_quota"]),
        "fee_min": fee_min,
        "fee_max": fee_max,
        "college_type": _normalize_college_type(college_type),
        "eligible_institutes": eligible_institutes,
        "eligible_count": len(eligible_institutes),
        "matched_predicted_field": matched_predicted_field,
    }

    if include_accuracy:
        segment = _estimate_segment_accuracy(model_bundle, rank, category, quota)
        response.update(
            {
                "estimated_input_accuracy": segment.get("estimated_accuracy"),
                "similar_rows_used": segment.get("matched_rows", 0),
                "rank_window": segment.get("window", 0),
                "model_training_accuracy": model_bundle.get("training_accuracy"),
                "evaluated_samples": model_bundle.get("total_samples", 0),
            }
        )

    return response, model_bundle


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

    return None


def _match_encoder_label(raw_value, encoder):
    """Map a normalized input value to the exact encoder class label."""
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value:
        return value

    classes = [str(item) for item in getattr(encoder, "classes_", [])]
    if value in classes:
        return value

    normalized_value = value.casefold().replace("_", " ").replace("-", " ").strip()
    for label in classes:
        normalized_label = label.casefold().replace("_", " ").replace("-", " ").strip()
        if normalized_label == normalized_value:
            return label

    return value


def _predict_field(model_bundle, rank, category, quota):
    """Run model inference for one input and return the predicted field."""
    if not category:
        category = model_bundle["default_category"]
    if not quota:
        quota = model_bundle["default_quota"]

    category = standardize_category(category)
    quota = standardize_quota(quota)
    category = _match_encoder_label(category, model_bundle["category_encoder"])
    quota = _match_encoder_label(quota, model_bundle["quota_encoder"])

    category_encoded = model_bundle["category_encoder"].transform([category])[0]
    quota_encoded = model_bundle["quota_encoder"].transform([quota])[0]
    prediction_features = pd.DataFrame(
        [[rank, category_encoded, quota_encoded]],
        columns=["rank", "category", "quota"],
    )
    prediction_encoded = model_bundle["model"].predict(prediction_features)[0]
    return model_bundle["target_encoder"].inverse_transform([prediction_encoded])[0]


def _estimate_segment_accuracy(model_bundle, rank, category, quota):
    """Estimate expected accuracy for selected inputs using historical rows."""
    dataset = load_prediction_dataset().copy()
    if dataset.empty:
        return {"estimated_accuracy": None, "matched_rows": 0, "window": 0}

    selected_category = standardize_category(category or model_bundle["default_category"])
    selected_quota = standardize_quota(quota or model_bundle["default_quota"])
    filtered = dataset[
        (dataset["category"].astype(str).str.casefold() == str(selected_category).casefold())
        & (dataset["quota"].astype(str).str.casefold() == str(selected_quota).casefold())
    ].copy()

    if filtered.empty:
        return {"estimated_accuracy": None, "matched_rows": 0, "window": 0}

    windows = [500, 2000, 5000]
    for window in windows:
        local = filtered[(filtered["rank"] >= (rank - window)) & (filtered["rank"] <= (rank + window))].copy()
        if len(local) >= 25:
            break
    else:
        local = filtered
        window = 0

    predicted_values = []
    actual_values = local["admission_field"].astype(str).tolist()
    for _, row in local.iterrows():
        try:
            predicted_values.append(_predict_field(model_bundle, int(row["rank"]), row["category"], row["quota"]))
        except Exception:
            predicted_values.append(None)

    comparable_pairs = [
        (predicted, actual)
        for predicted, actual in zip(predicted_values, actual_values)
        if predicted is not None
    ]
    if not comparable_pairs:
        return {"estimated_accuracy": None, "matched_rows": 0, "window": window}

    matches = sum(
        1
        for predicted, actual in comparable_pairs
        if str(predicted).strip().casefold() == str(actual).strip().casefold()
    )
    estimated_accuracy = round(matches / len(comparable_pairs), 4)
    return {
        "estimated_accuracy": estimated_accuracy,
        "matched_rows": len(comparable_pairs),
        "window": window,
    }


@app.after_request
def add_cors_headers(response):
    """Allow the frontend to call the API from the browser."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@lru_cache(maxsize=1)
def load_model_bundle():
    """Load the trained model and encoders with fallback to dataset-based encoders."""
    model_file = _resolve_model_file()
    if not model_file or not DATA_FILE.exists():
        return None

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
    dataset = dataset.dropna(subset=["category", "quota", "admission_field"]).copy()
    default_category = dataset["category"].astype(str).mode().iat[0] if not dataset.empty else PREDICTION_DEFAULTS["category"]
    default_quota = dataset["quota"].astype(str).mode().iat[0] if not dataset.empty else PREDICTION_DEFAULTS["quota"]
    if category_encoder is None or quota_encoder is None or target_encoder is None:
        _, category_encoder, quota_encoder, target_encoder = encode_training_data(dataset)

    training_accuracy = None
    total_samples = 0
    try:
        category_values = [_match_encoder_label(value, category_encoder) for value in dataset["category"].astype(str)]
        quota_values = [_match_encoder_label(value, quota_encoder) for value in dataset["quota"].astype(str)]
        actual_values = [_match_encoder_label(value, target_encoder) for value in dataset["admission_field"].astype(str)]

        encoded_features = pd.DataFrame(
            {
                "rank": dataset["rank"].astype(int).tolist(),
                "category": category_encoder.transform(category_values),
                "quota": quota_encoder.transform(quota_values),
            }
        )
        predicted_encoded = model.predict(encoded_features)
        predicted_values = target_encoder.inverse_transform(predicted_encoded)
        total_samples = len(predicted_values)
        if total_samples > 0:
            matches = sum(
                1
                for predicted, actual in zip(predicted_values, actual_values)
                if str(predicted).strip().casefold() == str(actual).strip().casefold()
            )
            training_accuracy = round(matches / total_samples, 4)
    except Exception:
        training_accuracy = None
        total_samples = 0

    return {
        "model": model,
        "category_encoder": category_encoder,
        "quota_encoder": quota_encoder,
        "target_encoder": target_encoder,
        "default_category": default_category,
        "default_quota": default_quota,
        "model_file": str(model_file),
        "training_accuracy": training_accuracy,
        "total_samples": total_samples,
    }


@app.route("/")
def home():
    """Serve the frontend page."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/predict", methods=["POST"])
def predict():
    """Predict the admission field using the trained model."""
    payload = request.get_json(silent=True) or {}

    try:
        rank = int(payload.get("rank"))
        category = payload.get("category")
        category = str(category).strip() or None if category is not None else None
        quota = payload.get("quota")
        quota = str(quota).strip() or None if quota is not None else None
        fee_min = _parse_optional_int(payload.get("fee_min"))
        fee_max = _parse_optional_int(payload.get("fee_max"))
        college_type = payload.get("college_type")
        college_type = str(college_type).strip() or None if college_type is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "Rank must be a valid number."}), 400

    if fee_min is not None and fee_max is not None and fee_min > fee_max:
        fee_min, fee_max = fee_max, fee_min

    try:
        response, model_bundle = _build_prediction_response(
            rank=rank,
            category=category,
            quota=quota,
            fee_min=fee_min,
            fee_max=fee_max,
            college_type=college_type,
            include_accuracy=False,
        )
    except ValueError:
        return jsonify({"error": "Category or quota is not recognized by the trained model."}), 400

    if not response or not model_bundle:
        return jsonify(
            {
                "error": "Trained model file was not found. Expected one of: model/model.pkl, model/trained_model.pkl, models/model.pkl, idel/model.pkl"
            }
        ), 500

    return jsonify(response)


@app.route("/predict/check", methods=["POST"])
def check_prediction_accuracy():
    """Return prediction plus estimated accuracy for selected input values."""
    payload = request.get_json(silent=True) or {}

    try:
        rank = int(payload.get("rank"))
        category = payload.get("category")
        category = str(category).strip() or None if category is not None else None
        quota = payload.get("quota")
        quota = str(quota).strip() or None if quota is not None else None
        fee_min = _parse_optional_int(payload.get("fee_min"))
        fee_max = _parse_optional_int(payload.get("fee_max"))
        college_type = payload.get("college_type")
        college_type = str(college_type).strip() or None if college_type is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "Rank must be a valid number."}), 400

    if fee_min is not None and fee_max is not None and fee_min > fee_max:
        fee_min, fee_max = fee_max, fee_min

    try:
        response, model_bundle = _build_prediction_response(
            rank=rank,
            category=category,
            quota=quota,
            fee_min=fee_min,
            fee_max=fee_max,
            college_type=college_type,
            include_accuracy=True,
        )
    except ValueError:
        return jsonify({"error": "Category or quota is not recognized by the trained model."}), 400

    if not response or not model_bundle:
        return jsonify({"error": "Trained model file was not found."}), 500

    return jsonify(response)


@app.route("/style.css")
def style():
    """Serve the frontend stylesheet."""
    return send_from_directory(FRONTEND_DIR, "style.css")


@app.route("/script.js")
def script():
    """Serve the frontend JavaScript file."""
    return send_from_directory(FRONTEND_DIR, "script.js")


@app.route("/api/options")
def options():
    """Return filter options for the institute search UI."""
    dataset = load_institute_search_dataset()
    prediction_dataset = load_prediction_dataset()

    allowed_keys = None
    master_institutes = None
    institute_master = load_institute_master_dataset()
    if institute_master is not None:
        master_institutes = institute_master["institute_name"].tolist()
        allowed_keys = set(institute_master["_dedupe_key"].tolist())
        dataset["_institute_key"] = dataset["institute_name"].astype(str).map(normalize_text)
        dataset = dataset[dataset["_institute_key"].isin(allowed_keys)]

    branches = sorted(_unique_values(dataset, "course_name"))
    if master_institutes is not None:
        institutes = sorted(master_institutes)
        cities = sorted({infer_city(name) for name in master_institutes if str(name).strip()})
    else:
        cities = sorted(_unique_values(dataset, "city"))
        institutes = sorted(_unique_values(dataset, "institute_name"))
    boys_hostel_options = sorted(_unique_values(dataset, "boys_hostel"))
    girls_hostel_options = sorted(_unique_values(dataset, "girls_hostel"))
    categories = sorted(_unique_values(prediction_dataset, "category"))
    quotas = sorted(_unique_values(prediction_dataset, "quota"))
    return jsonify(
        {
            "branches": branches,
            "cities": cities,
            "institutes": institutes,
            "boys_hostel": boys_hostel_options,
            "girls_hostel": girls_hostel_options,
            "categories": categories,
            "quotas": quotas,
        }
    )


@app.route("/api/search-institutes")
def search_institutes():
    """Search institutes from the fee dataset by institute name, branch, and city."""
    institute_name = request.args.get("institute_name", "").strip()
    branch = request.args.get("branch", "").strip()
    city = request.args.get("city", "").strip()
    college_type = request.args.get("college_type", "").strip()
    limit = request.args.get("limit", "100")

    fee_dataset = load_fee_recommendation_dataset().copy()
    
    if fee_dataset.empty:
        return jsonify({"results": []})

    # Apply filters
    if institute_name:
        fee_dataset = fee_dataset[
            fee_dataset["institute_name"].astype(str).str.strip().str.casefold().str.contains(institute_name.casefold(), na=False)
        ]
    
    if branch:
        fee_dataset = fee_dataset[
            fee_dataset["course_name"].astype(str).str.strip().str.casefold() == branch.casefold()
        ]
    
    if city:
        fee_dataset = fee_dataset[
            fee_dataset["city"].astype(str).str.strip().str.casefold() == city.casefold()
        ]
    
    if college_type:
        fee_dataset = fee_dataset[
            fee_dataset["college_type"].astype(str).str.strip().str.casefold() == college_type.casefold()
        ]
    
    # Limit results
    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 100
    
    limit_value = max(1, min(limit_value, 500))
    results = _json_safe_records(
        fee_dataset[
            ["institute_name", "course_name", "admission_field", "college_type", "city", "official_website", "tuition_fee"]
        ].head(limit_value)
    )
    
    return jsonify({"results": results})


@app.route("/api/filter")
def filter_institutes():
    """Filter the admissions dataset by institute, branch, and hostel availability."""
    admissions_dataset = load_institute_search_dataset().copy()
    branch = request.args.get("branch", "").strip()
    city = request.args.get("city", "").strip()
    institute_name = request.args.get("institute_name", "").strip()
    boys_hostel = request.args.get("boys_hostel", "").strip()
    girls_hostel = request.args.get("girls_hostel", "").strip()
    limit = request.args.get("limit", "10")
    page = request.args.get("page", "1")
    show_all = str(limit).strip().casefold() == "all"

    # Enforce institue_master1.csv as the source-of-truth when available.
    institute_master_source = load_institute_master_dataset()
    if institute_master_source is not None:
        institute_master = institute_master_source.copy()

        # Branch filter is derived from admissions but applied on master institute keys.
        if branch and "course_name" in admissions_dataset.columns:
            branch_filtered = admissions_dataset[
                admissions_dataset["course_name"].astype(str).str.strip().str.casefold() == branch.casefold()
            ].copy()
            branch_keys = set(branch_filtered["institute_name"].astype(str).map(normalize_text).tolist())
            institute_master = institute_master[institute_master["_dedupe_key"].isin(branch_keys)]

        if city:
            institute_master = institute_master[
                institute_master["city"].astype(str).str.strip().str.casefold() == city.casefold()
            ]
        if institute_name:
            institute_master = institute_master[
                institute_master["institute_name"].astype(str).str.strip().str.casefold() == institute_name.casefold()
            ]
        if boys_hostel:
            institute_master = institute_master[
                institute_master["boys_hostel"].astype(str).str.strip().str.casefold() == boys_hostel.casefold()
            ]
        if girls_hostel:
            institute_master = institute_master[
                institute_master["girls_hostel"].astype(str).str.strip().str.casefold() == girls_hostel.casefold()
            ]

        filtered = institute_master[["institute_name", "city", "boys_hostel", "girls_hostel", "official_website", "_dedupe_key"]].copy()
    else:
        dataset = admissions_dataset
        if branch:
            dataset = dataset[dataset["course_name"].astype(str).str.strip().str.casefold() == branch.casefold()]
        if city and "city" in dataset.columns:
            dataset = dataset[dataset["city"].astype(str).str.strip().str.casefold() == city.casefold()]
        if institute_name:
            dataset = dataset[dataset["institute_name"].astype(str).str.strip().str.casefold() == institute_name.casefold()]
        if boys_hostel and "boys_hostel" in dataset.columns:
            dataset = dataset[dataset["boys_hostel"].astype(str).str.strip().str.casefold() == boys_hostel.casefold()]
        if girls_hostel and "girls_hostel" in dataset.columns:
            dataset = dataset[dataset["girls_hostel"].astype(str).str.strip().str.casefold() == girls_hostel.casefold()]

        columns = [
            column
            for column in [
                "institute_name",
                "city",
                "boys_hostel",
                "girls_hostel",
                "official_website",
            ]
            if column in dataset.columns
        ]

        filtered = dataset[columns].fillna("")
        filtered["institute_name"] = filtered["institute_name"].astype(str).str.strip()
        filtered["_dedupe_key"] = filtered["institute_name"].map(normalize_text)
        if "official_website" in filtered.columns:
            filtered["_has_website"] = filtered["official_website"].astype(str).str.strip() != ""
            filtered = filtered.sort_values(["_dedupe_key", "_has_website"], ascending=[True, False])
        filtered = filtered.drop_duplicates(subset=["_dedupe_key"])
        filtered = filtered.sort_values(["institute_name"], ascending=[True])

    try:
        limit_value = int(limit)
    except (TypeError, ValueError):
        limit_value = 10

    try:
        page_value = int(page)
    except (TypeError, ValueError):
        page_value = 1

    page_value = max(1, page_value)

    total_count = len(filtered)
    if show_all:
        limit_value = total_count if total_count > 0 else 1
        total_pages = 1
        page_value = 1
    else:
        limit_value = max(1, min(limit_value, 100))
        total_pages = max(1, ceil(total_count / limit_value))
        page_value = min(page_value, total_pages)
        start_index = (page_value - 1) * limit_value
        end_index = start_index + limit_value
        filtered = filtered.iloc[start_index:end_index]

    if "_has_website" in filtered.columns:
        filtered = filtered.drop(columns=["_has_website"])
    if "_dedupe_key" in filtered.columns:
        filtered = filtered.drop(columns=["_dedupe_key"])

    return jsonify(
        {
            "results": _json_safe_records(filtered),
            "page": page_value,
            "page_size": limit_value,
            "show_all": show_all,
            "total": total_count,
            "total_pages": total_pages,
        }
    )


def _unique_values(dataframe, column_name):
    """Collect sorted, non-empty string values from a dataframe column."""
    if column_name not in dataframe.columns:
        return []

    values = set()
    for value in dataframe[column_name].astype(str):
        cleaned_value = value.strip()
        if cleaned_value and cleaned_value.casefold() != "nan":
            values.add(cleaned_value)
    return values


if __name__ == "__main__":
    # Preload data on startup to warm up caches
    print("Loading data files...")
    try:
        load_institute_master_dataset()
        load_fee_recommendation_dataset()
        load_institute_search_dataset()
        load_prediction_dataset()
        load_model_bundle()
        print("✓ Data loaded successfully!")
    except Exception as e:
        print(f"Warning: Could not preload data: {e}")
    
    print("Starting Flask server...")
    app.run(debug=False, host="127.0.0.1", port=5000)