import json
import pickle
from pathlib import Path
import lightgbm as lgb

MODELS_DIR = Path("models")

def load_config():
    with open(MODELS_DIR / "config.json", "r") as f:
        return json.load(f)

def load_sarimax():
    with open(MODELS_DIR / "sarimax_fit.pkl", "rb") as f:
        return pickle.load(f)

def load_boosting_models(max_horizon: int):
    xgb_models = {}
    lgb_models = {}

    for h in range(1, max_horizon + 1):
        with open(MODELS_DIR / f"xgb_h{h}.pkl", "rb") as f:
            xgb_models[h] = pickle.load(f)

        lgb_models[h] = lgb.Booster(model_file=str(MODELS_DIR / f"lgb_h{h}.txt"))

    return xgb_models, lgb_models