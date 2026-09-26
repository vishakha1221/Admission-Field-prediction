# Admission Field Prediction System

This project is a Flask + frontend Admission Field Prediction System.

The application predicts an admission field from rank, category, and quota, then lists matching institutes with hostel, city, fee, and website information. Training and inference share the same cleaning, normalization, and encoding contract.

## Project Structure

- `data/` - source CSV/XLSX admission data and institute metadata
- `model/model.pkl` - generated model bundle containing the model, encoders, metrics, and feature order
- `backend/` - shared preprocessing and Flask API
- `frontend/` - HTML, CSS, and JavaScript user interface
- `notebook/model_training.py` - model comparison and artifact generation
- `requirements.txt` - Python dependencies

## How To Run

1. Install Python dependencies:

	```bash
	pip install -r requirements.txt
	```

2. Start the Flask server:

	```bash
	python backend/app.py
	```

If `model/model.pkl` does not exist, train it first:

	```bash
	python notebook/model_training.py
	```

3. Open your browser and visit:

	```
	http://127.0.0.1:5000/
	```

4. Fill in the form and click Predict.

The app will send the form data to `POST /predict` and display the predicted admission field:

The backend expects:

- `rank`
- `category`
- `quota`

The page also includes an institute search panel where you can filter by branch, institute name, and hostel availability.

## Future Work

The model is selected using held-out accuracy, precision, recall, weighted F1, and three-fold cross-validation. XGBoost and LightGBM are included automatically when installed.
