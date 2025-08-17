import json
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
import pickle

# Load dataset
with open('nail_polish_dataset.json', 'r') as f:
    data = json.load(f)

df = pd.DataFrame(data)

# Features and label
features = ["skin_tone", "dress_color", "occasion", "finish_type", "age_group"]
label_col = "recommended_shade"

# Show label distribution
print("Label distribution:\n", df[label_col].value_counts())

# Split data
X = df[features]
y = df[label_col]
X_train_raw, X_test_raw, y_train_raw, y_test_raw = train_test_split(X, y, test_size=0.2, random_state=42)

# Encode features
encoders = {}
X_train = pd.DataFrame()
X_test = pd.DataFrame()
for col in features:
    le = LabelEncoder()
    X_train[col] = le.fit_transform(X_train_raw[col])
    X_test[col] = le.transform(X_test_raw[col])
    encoders[col] = le

# Encode labels
le_label = LabelEncoder()
y_train = le_label.fit_transform(y_train_raw)
y_test = le_label.transform(y_test_raw)
encoders[label_col] = le_label

# Train model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate
accuracy = model.score(X_test, y_test)
print("Model Accuracy:", accuracy)

# Save model and encoders
with open('nail_polish_model.pkl', 'wb') as f:
    pickle.dump(model, f)
with open('label_encoders.pkl', 'wb') as f:
    pickle.dump(encoders, f)

# Example prediction
sample_input = X_test.iloc[0:1]
predicted_index = model.predict(sample_input)[0]
predicted_label = le_label.inverse_transform([predicted_index])[0]
print("\nSample prediction:")
print("Input:", X_test_raw.iloc[0])
print("Predicted Shade:", predicted_label)