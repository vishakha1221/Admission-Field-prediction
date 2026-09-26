"""Train and persist the best admission-field classifier."""

from pathlib import Path
import sys

import joblib
from sklearn.ensemble import AdaBoostClassifier, ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score, train_test_split
from sklearn.tree import DecisionTreeClassifier

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_FILE = BASE_DIR / "model" / "model.pkl"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.preprocess import FEATURE_COLUMNS, TARGET_COLUMN, encode_training_data, load_prediction_dataset


def build_models():
    """Return built-in candidates and optional third-party models."""
    models = {
        "Decision Tree": DecisionTreeClassifier(max_depth=20, min_samples_leaf=2, random_state=42),
        "Random Forest": RandomForestClassifier(n_estimators=150, min_samples_leaf=2, n_jobs=-1, random_state=42),
        "Extra Trees": ExtraTreesClassifier(n_estimators=150, min_samples_leaf=2, n_jobs=-1, random_state=42),
        "Gradient Boosting": GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
        "AdaBoost": AdaBoostClassifier(n_estimators=100, random_state=42),
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = XGBClassifier(
            n_estimators=150, max_depth=6, learning_rate=0.08, subsample=0.9,
            colsample_bytree=0.9, objective="multi:softprob", eval_metric="mlogloss",
            n_jobs=2, random_state=42,
        )
    except ImportError:
        pass
    try:
        from lightgbm import LGBMClassifier
        models["LightGBM"] = LGBMClassifier(n_estimators=150, learning_rate=0.08, verbosity=-1, random_state=42)
    except ImportError:
        pass
    return models


def evaluate_model(name, estimator, features, target, x_train, x_test, y_train, y_test):
    """Fit a candidate, calculate holdout metrics, and run cross-validation."""
    estimator.fit(x_train, y_train)
    predictions = estimator.predict(x_test)
    class_counts = target.value_counts()
    folds = StratifiedKFold(n_splits=3, shuffle=True, random_state=42) if class_counts.min() >= 3 else KFold(n_splits=3, shuffle=True, random_state=42)
    cv_accuracy = float(cross_val_score(estimator, features, target, cv=folds, scoring="accuracy", n_jobs=1).mean())
    metrics = {
        "model": name,
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions, average="weighted", zero_division=0)),
        "recall": float(recall_score(y_test, predictions, average="weighted", zero_division=0)),
        "f1": float(f1_score(y_test, predictions, average="weighted", zero_division=0)),
        "cross_validation_accuracy": cv_accuracy,
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
    }
    print(f"{name}: accuracy={metrics['accuracy']:.4f}, precision={metrics['precision']:.4f}, recall={metrics['recall']:.4f}, f1={metrics['f1']:.4f}, cv={cv_accuracy:.4f}")
    return estimator, metrics


def main():
    dataset = load_prediction_dataset()
    encoded, category_encoder, quota_encoder, target_encoder = encode_training_data(dataset)
    features = encoded[FEATURE_COLUMNS]
    target = encoded[TARGET_COLUMN]
    stratify_target = target if target.value_counts().min() >= 2 else None
    x_train, x_test, y_train, y_test = train_test_split(features, target, test_size=0.2, random_state=42, stratify=stratify_target)

    results = []
    for name, estimator in build_models().items():
        try:
            results.append(evaluate_model(name, estimator, features, target, x_train, x_test, y_train, y_test))
        except Exception as error:
            print(f"Skipping {name}: {error}")
    if not results:
        raise RuntimeError("No candidate model could be trained")

    best_model, best_metrics = max(results, key=lambda item: (item[1]["f1"], item[1]["cross_validation_accuracy"]))
    best_model.fit(features, target)
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": best_model,
        "category_encoder": category_encoder,
        "quota_encoder": quota_encoder,
        "target_encoder": target_encoder,
        "feature_order": FEATURE_COLUMNS,
        "target_column": TARGET_COLUMN,
        "metrics": best_metrics,
        "training_rows": len(dataset),
    }, MODEL_FILE)
    print(f"Best model: {best_metrics['model']}")
    print(f"Saved model bundle to: {MODEL_FILE}")


if __name__ == "__main__":
    main()
