"""Create demo model files in ./sample_models for the viva:
   student_v1.pkl, student_v2.pkl  -> valid RandomForest models
   faulty_model.pkl                -> corrupt file (must be rejected)"""
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

out = Path(__file__).resolve().parents[1] / "sample_models"
out.mkdir(exist_ok=True)

rng = np.random.default_rng(42)
X = rng.uniform(0, 10, size=(300, 3))            # study hours, attendance, past score (scaled)
y = (X.sum(axis=1) + rng.normal(0, 2, 300) > 15).astype(int)

for name, trees in (("student_v1.pkl", 5), ("student_v2.pkl", 100)):
    model = RandomForestClassifier(n_estimators=trees, random_state=1).fit(X, y)
    joblib.dump(model, out / name)
    print("created", out / name, f"(train accuracy {model.score(X, y) * 100:.1f}%)")

(out / "faulty_model.pkl").write_bytes(b"this is not a real model")
print("created", out / "faulty_model.pkl")
