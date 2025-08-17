import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
from sklearn.preprocessing import OneHotEncoder
from pathlib import Path

# Model storage path
MODEL_PATH = Path("model") / "glossify_net.pth"

# ─── Model Architecture ───────────────────────────────
class GlossifyNet(nn.Module):
    def __init__(self, input_dim, hidden=64, output_dim=20):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, output_dim)
        )

    def forward(self, x):
        return self.net(x)

# ─── Global encoder ───────────────────────────────────
encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')

# ─── Dataset Loader ───────────────────────────────────
def _load_dataset(csv_path="model/nail_polish_training.csv"):
    df = pd.read_csv(csv_path)
    X_raw = df[["skin_tone", "occasion", "finish_type"]].astype(str)
    y = df["polish_id"].astype(int)
    X = encoder.fit_transform(X_raw)
    return torch.tensor(X, dtype=torch.float32), torch.tensor(y), encoder, int(y.max()) + 1

# ─── Model Trainer ────────────────────────────────────
def train_model(csv_path="model/nail_polish_training.csv", epochs=50, lr=0.001):
    X, y, enc, output_dim = _load_dataset(csv_path)
    input_dim = X.shape[1]
    model = GlossifyNet(input_dim=input_dim, output_dim=output_dim)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    for epoch in range(epochs):
        optimizer.zero_grad()
        logits = model(X)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

    MODEL_PATH.parent.mkdir(exist_ok=True)
    torch.save({"model": model.state_dict(), "encoder": enc, "input_dim": input_dim, "output_dim": output_dim}, MODEL_PATH)
    return loss.item()

# ─── Load Model ───────────────────────────────────────
def _load_model():
    if not MODEL_PATH.exists():
        return None, None
    data = torch.load(MODEL_PATH, map_location="cpu")
    model = GlossifyNet(data["input_dim"], output_dim=data["output_dim"])
    model.load_state_dict(data["model"])
    model.eval()
    return model, data["encoder"]

model, encoder = _load_model()

# ─── Recommendation Logic ─────────────────────────────
def recommend_polishes(user_input: dict, k=3):
    """
    user_input = {
        'skin_tone': 'fair',
        'occasion': 'party',
        'finish_type': 'glossy'
    }
    """
    global model, encoder
    if model is None or encoder is None:
        return []

    X = encoder.transform([[
        user_input["skin_tone"],
        user_input["occasion"],
        user_input["finish_type"]
    ]])

    logits = model(torch.tensor(X, dtype=torch.float32))
    topk = logits.softmax(1).topk(k)
    return topk.indices[0].tolist()
