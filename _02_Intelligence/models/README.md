# 02_Intelligence/models/

This directory stores TFT quantile regression weights (.pth files).

## Files expected:
- `tft_v1.3.pth`  — main TFT model checkpoint (Darts TFTModel)
- `vsn_weights.json` — Variable Selection Network learned weights per ward

## Training:
Run from repo root:
    python 02_Intelligence/tft_engine.py --train

## Download pre-trained weights:
    python 02_Intelligence/tft_engine.py --download-weights

If weights are missing, `tft_engine.py` falls back to a statistical
forecast (mean-reversion + ward-specific variance). Accuracy is lower
but the system remains operational.
