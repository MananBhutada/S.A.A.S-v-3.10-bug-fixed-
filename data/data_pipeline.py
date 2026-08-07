"""
data/data_pipeline.py
Project S.A.A.S. — Data Pipeline
==================================
Generates, cleans, and prepares the Delhi AQI training dataset.
Also re-trains the quantile models when new data arrives.

Run:
    python data/data_pipeline.py --generate   # regenerate dataset
    python data/data_pipeline.py --train      # retrain models
    python data/data_pipeline.py --all        # both
"""
import argparse, json, logging, os, sys
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("PIPELINE")

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "02_Intelligence", "models")

WARD_PROFILES = {
    "Narela":          {"base_pm25": 185, "base_no2": 48, "base_co": 1800},
    "Alipur":          {"base_pm25": 175, "base_no2": 44, "base_co": 1600},
    "Rohini":          {"base_pm25": 148, "base_no2": 52, "base_co": 1400},
    "Dwarka":          {"base_pm25": 138, "base_no2": 46, "base_co": 1200},
    "Karawal Nagar":   {"base_pm25": 162, "base_no2": 50, "base_co": 1500},
    "Mustafabad":      {"base_pm25": 155, "base_no2": 48, "base_co": 1350},
    "Saket":           {"base_pm25": 112, "base_no2": 62, "base_co":  950},
    "Lajpat Nagar":    {"base_pm25": 118, "base_no2": 65, "base_co":  980},
    "Connaught Place": {"base_pm25": 102, "base_no2": 72, "base_co":  920},
    "Chandni Chowk":   {"base_pm25": 128, "base_no2": 68, "base_co": 1100},
}

MONTHLY_MULT = [1.80,1.60,1.25,0.90,0.80,0.65,0.50,0.48,0.58,0.90,1.45,1.90]
HOURLY_MULT  = [1.22,1.28,1.25,1.18,1.10,1.02,0.98,0.96,
                1.12,1.28,1.22,1.08,0.98,0.94,0.90,0.92,
                0.96,1.05,1.18,1.32,1.38,1.35,1.30,1.25]
WEEKDAY_MULT = [1.06,1.08,1.08,1.08,1.06,0.94,0.90]
MONTHLY_WIND_SPEED = [4.2,5.1,6.8,8.2,9.5,10.2,12.1,11.8,8.4,5.5,3.8,3.5]
MONTHLY_WIND_DIR   = [250,260,270,290,290,220,200,210,240,260,250,245]

def pm25_to_aqi(pm25):
    for lo,hi,alo,ahi in [(0,30,0,50),(30,60,51,100),(60,90,101,200),
                           (90,120,201,300),(120,250,301,400),(250,500,401,500)]:
        if lo <= pm25 <= hi:
            return round(alo + (pm25-lo)*(ahi-alo)/(hi-lo))
    return 500

def generate_dataset(start_year=2022, end_year=2025, seed=42):
    np.random.seed(seed)
    from datetime import datetime, timedelta
    import math

    rows, dt = [], datetime(start_year, 1, 1)
    end = datetime(end_year, 1, 1)
    while dt < end:
        m_m = MONTHLY_MULT[dt.month-1]
        h_m = HOURLY_MULT[dt.hour]
        w_m = WEEKDAY_MULT[dt.weekday()]
        stubble_f = (1.0 + 0.35*((dt.day-15)/16) if dt.month==10 and dt.day>=15
                     else 1.35 if dt.month==11 else 1.0)
        spd = max(0.5, np.random.lognormal(np.log(MONTHLY_WIND_SPEED[dt.month-1]), 0.30))
        brg = (MONTHLY_WIND_DIR[dt.month-1] + np.random.normal(0,20)) % 360
        u   = -spd * math.sin(math.radians(brg))
        v   = -spd * math.cos(math.radians(brg))

        for ward, p in WARD_PROFILES.items():
            is_gw  = ward in ("Narela","Alipur")
            gw_ext = 1.0 + (max(0, spd-15)/15)*0.35 if is_gw else 1.0
            pm25   = max(8, min(450, p["base_pm25"]*m_m*h_m*w_m*stubble_f*gw_ext
                                + np.random.normal(0, p["base_pm25"]*0.10)))
            no2    = max(5, p["base_no2"]*m_m*h_m*w_m + np.random.normal(0,7))
            co     = max(100, p["base_co"]*m_m*h_m*w_m + np.random.normal(0,120))
            pm10   = max(10, pm25*np.random.uniform(1.55,1.95))
            so2    = max(2, 12*m_m + np.random.normal(0,3))
            o3     = max(5, 35*(1-0.35*m_m/1.9)*h_m + np.random.normal(0,7))
            co_n   = min(1, co/2000)
            mie    = max(0.1, min(0.95, 0.78-co_n*0.45+np.random.normal(0,0.07)))
            rows.append({
                "timestamp": dt.isoformat(), "ward": ward,
                "pm25": round(pm25,1), "pm10": round(pm10,1),
                "no2_ppb": round(no2,1), "co_ppb": round(co,1),
                "so2_ppb": round(so2,1), "o3_ppb": round(o3,1),
                "aqi": pm25_to_aqi(pm25),
                "wind_speed_kmh": round(spd,2), "wind_bearing_deg": round(brg,1),
                "wind_u": round(u,2), "wind_v": round(v,2),
                "mie_index": round(mie,3),
                "month": dt.month, "hour": dt.hour, "weekday": dt.weekday(),
                "is_gateway": int(is_gw), "stubble_season": int(stubble_f > 1.1),
            })
        dt += pd.Timedelta(hours=1)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(DATA_DIR, "delhi_aqi_2022_2025.csv"), index=False)
    log.info("Generated %d rows", len(df))
    return df

def clean_and_feature(df=None):
    if df is None:
        df = pd.read_csv(os.path.join(DATA_DIR,"delhi_aqi_2022_2025.csv"), parse_dates=["timestamp"])
    df = df.sort_values(["ward","timestamp"]).reset_index(drop=True)
    for col,(lo,hi) in [("pm25",(0,450)),("pm10",(0,800)),("no2_ppb",(0,200)),
                         ("co_ppb",(0,5000)),("aqi",(0,500)),("mie_index",(0,1))]:
        df[col] = df[col].clip(lo, hi)
    import math
    for ward in df["ward"].unique():
        m = df["ward"]==ward
        for lag in [1,6,24]:
            df.loc[m, f"pm25_lag{lag}h"] = df.loc[m,"pm25"].shift(lag)
        df.loc[m,"pm25_rolling6h"]  = df.loc[m,"pm25"].shift(1).rolling(6).mean()
        df.loc[m,"pm25_rolling24h"] = df.loc[m,"pm25"].shift(1).rolling(24).mean()
        df.loc[m,"aqi_lag1h"]  = df.loc[m,"aqi"].shift(1)
        df.loc[m,"aqi_lag24h"] = df.loc[m,"aqi"].shift(24)
    df["hour_sin"]  = np.sin(2*np.pi*df["hour"]/24)
    df["hour_cos"]  = np.cos(2*np.pi*df["hour"]/24)
    df["month_sin"] = np.sin(2*np.pi*(df["month"]-1)/12)
    df["month_cos"] = np.cos(2*np.pi*(df["month"]-1)/12)
    df["dow_sin"]   = np.sin(2*np.pi*df["weekday"]/7)
    df["dow_cos"]   = np.cos(2*np.pi*df["weekday"]/7)
    df = df.dropna().reset_index(drop=True)
    df["split"] = "train"
    df.loc[df["timestamp"] >= "2024-07-01","split"] = "val"
    df.loc[df["timestamp"] >= "2024-10-01","split"] = "test"
    df.to_csv(os.path.join(DATA_DIR,"delhi_aqi_clean.csv"), index=False)
    log.info("Clean dataset: %d rows, %d cols", len(df), len(df.columns))
    return df

def train_models(df=None):
    import joblib
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    if df is None:
        df = pd.read_csv(os.path.join(DATA_DIR,"delhi_aqi_clean.csv"), parse_dates=["timestamp"])

    FEAT = ["pm25","pm10","no2_ppb","co_ppb","mie_index","wind_speed_kmh","wind_u","wind_v",
            "pm25_lag1h","pm25_lag24h","aqi_lag1h","aqi_lag24h",
            "hour_sin","hour_cos","month_sin","month_cos","stubble_season","is_gateway"]

    sample = df[df["split"]=="train"].groupby(["ward","month"], group_keys=False)\
               .apply(lambda g: g.sample(min(len(g),200), random_state=42)).reset_index(drop=True)
    val  = df[df["split"]=="val"]
    test = df[df["split"]=="test"]

    Xtr,ytr = sample[FEAT].values, sample["aqi"].values
    Xv,yv   = val[FEAT].values, val["aqi"].values
    Xt,yt   = test[FEAT].values, test["aqi"].values

    models = {}
    for q, alpha in [("p10",0.10),("p50",0.50),("p90",0.90)]:
        log.info("Training %s quantile model...", q)
        m = GradientBoostingRegressor(
            loss="quantile", alpha=alpha,
            n_estimators=150, max_depth=5,
            learning_rate=0.08, subsample=0.85,
            min_samples_leaf=10, random_state=42,
        )
        m.fit(Xtr, ytr)
        p   = m.predict(Xv)
        mae = mean_absolute_error(yv, p)
        log.info("  %s Val MAE=%.1f", q, mae)
        models[q] = m

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(models, os.path.join(MODEL_DIR,"quantile_models.pkl"))
    joblib.dump(FEAT,   os.path.join(MODEL_DIR,"feature_cols.pkl"))

    test_metrics = {}
    for ward in sorted(df["ward"].unique()):
        msk = (test["ward"]==ward).values
        p50 = models["p50"].predict(Xt[msk])
        yw  = yt[msk]
        test_metrics[ward] = {"mae": round(mean_absolute_error(yw,p50),1),
                               "rmse": round(np.sqrt(mean_squared_error(yw,p50)),1)}

    meta = {"model_name":"saas_gbq_v1","model_type":"GradientBoostingQuantile",
            "feature_cols":FEAT,"target_col":"aqi",
            "train_period":"2022-01-01 to 2024-06-30",
            "test_metrics":test_metrics,"wards":sorted(df["ward"].unique())}
    with open(os.path.join(MODEL_DIR,"model_meta.json"),"w") as f:
        json.dump(meta, f, indent=2)
    log.info("Models saved to %s", MODEL_DIR)
    return models

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--generate", action="store_true")
    p.add_argument("--train",    action="store_true")
    p.add_argument("--all",      action="store_true")
    args = p.parse_args()

    if args.all or args.generate:
        df = generate_dataset()
        df = clean_and_feature(df)
    if args.all or args.train:
        df = pd.read_csv(os.path.join(DATA_DIR,"delhi_aqi_clean.csv"), parse_dates=["timestamp"])
        train_models(df)
