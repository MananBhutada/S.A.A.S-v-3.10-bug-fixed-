/*
 * Hardware/sensor_calibration.h
 * Project S.A.A.S. — GP2Y1010AU0F Calibration Constants
 * =======================================================
 * Calibrated against CPCB reference monitor at Anand Vihar, Delhi.
 * Re-calibrate every 6 months or after sensor cleaning.
 *
 * Calibration procedure:
 *   1. Place node next to a reference PM2.5 monitor for 24h.
 *   2. Record raw ADC vs reference PM2.5 pairs every hour.
 *   3. Linear regression: PM2.5 = (V - ZERO_V) * SENSITIVITY * CORRECTION
 *   4. Update constants below and reflash via OTA.
 */

#ifndef SENSOR_CALIBRATION_H
#define SENSOR_CALIBRATION_H

// ── GP2Y1010AU0F Zero-Dust Voltage (V) ───────────────────────────────────────
// Output voltage in clean air (should be ~0.9V per datasheet)
// Measured: 0.92V on bench with HEPA-filtered air
#define DUST_SENSOR_ZERO_V          0.92f

// ── Sensitivity (mg/m³ per V) ─────────────────────────────────────────────────
// Per GP2Y1010 datasheet: 0.5 V/(mg/m³)  →  sensitivity = 1/0.5 = 2.0
// After field calibration at Anand Vihar: 1.95
#define DUST_SENSOR_SENSITIVITY     1.95f

// ── Delhi Ambient PM2.5 Correction Factor ────────────────────────────────────
// GP2Y1010 reads optical density; PM2.5 mass depends on particle density.
// Delhi particles have higher BC (black carbon) component → correction needed.
// Derived from co-location with CPCB BAM monitor, Oct–Nov 2025.
#define DELHI_PM25_CORRECTION_FACTOR  1.12f

// ── ADC Resolution ───────────────────────────────────────────────────────────
// ESP32 ADC: 12-bit (0–4095) at 3.3V reference
#define ADC_RESOLUTION              4095
#define ADC_VREF                    3.3f

// ── Pump Pressure → Droplet Size Mapping ─────────────────────────────────────
// Based on Stokes Number (Stk) optimization for PM2.5 capture:
//   Stk = (ρ_p × d_p² × U) / (18 × μ × d_c)
//   Target: Stk ≈ 0.1–0.8 for impaction efficiency > 60%
//
// Droplet diameter d_p vs pump pressure (bar):
//   1.0 bar  → ~60 μm  (too large, falls fast)
//   2.0 bar  → ~42 μm  (aggressive washout)
//   3.0 bar  → ~28 μm  (standard scrubbing)
//   4.0 bar  → ~18 μm  (fine mist, low PM)
//   5.0 bar  → ~12 μm  (near streamline limit)
//   >5.5 bar → <8 μm   (Streamline Effect — avoid, PM2.5 curves around)

#define STOKES_MIN_DROPLET_UM       10.0f
#define STOKES_MAX_DROPLET_UM       50.0f
#define PUMP_MAX_PRESSURE_BAR       6.0f

// ── Nozzle Yaw Response Coefficient ─────────────────────────────────────────
// Degrees of yaw servo change per degree of wind bearing change
#define NOZZLE_YAW_GAIN             0.5f

// ── Firmware Version ─────────────────────────────────────────────────────────
#define FIRMWARE_VERSION            "2.1.0"
#define NODE_TYPE                   "SAAS-SCRUBBER-ESP32"

#endif // SENSOR_CALIBRATION_H
