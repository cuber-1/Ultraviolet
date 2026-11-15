from __future__ import annotations

import math

from .profiles import CropProfile


FEATURE_NAMES = [
    "temperature_c", "annual_precipitation_mm", "soil_ph", "solar_mj_m2_day", "irrigated",
    "temp_opt_min", "temp_opt_max", "temp_abs_min", "temp_abs_max",
    "rain_opt_min", "rain_opt_max", "rain_abs_min", "rain_abs_max",
    "ph_opt_min", "ph_opt_max", "ph_abs_min", "ph_abs_max",
    "growing_days_min", "growing_days_max",
    "temperature_range_fit", "water_range_fit", "ph_range_fit", "solar_range_fit",
    "temperature_water_interaction", "ph_solar_interaction",
]

# These six input-derived features won the locked v0.11 compaction gate. They
# contain no crop identity or target value: the four memberships locate current
# conditions inside published EcoCrop ranges and the two interactions preserve
# the mechanistic relationships between those memberships.
COMPACT_FEATURE_NAMES = FEATURE_NAMES[-6:]
COMPACT_FEATURE_COLUMNS = [FEATURE_NAMES.index(name) for name in COMPACT_FEATURE_NAMES]


def trapezoid(value: float, absolute_min: float, optimum_min: float, optimum_max: float, absolute_max: float) -> float:
    if value <= absolute_min or value >= absolute_max:
        return 0.0
    if optimum_min <= value <= optimum_max:
        return 1.0
    if value < optimum_min:
        return (value - absolute_min) / max(1e-6, optimum_min - absolute_min)
    return (absolute_max - value) / max(1e-6, absolute_max - optimum_max)


def range_memberships(profile: CropProfile, temperature_c: float, annual_precipitation_mm: float, soil_ph: float, solar_mj_m2_day: float, irrigated: bool) -> tuple[float, float, float, float]:
    temperature = trapezoid(temperature_c, profile.temp_abs_min, profile.temp_opt_min, profile.temp_opt_max, profile.temp_abs_max)
    effective_rain = max(annual_precipitation_mm, profile.rain_opt_min) if irrigated else annual_precipitation_mm
    water = trapezoid(effective_rain, profile.rain_abs_min, profile.rain_opt_min, profile.rain_opt_max, profile.rain_abs_max)
    ph = trapezoid(soil_ph, profile.ph_abs_min, profile.ph_opt_min, profile.ph_opt_max, profile.ph_abs_max)
    solar = trapezoid(solar_mj_m2_day, 4.0, 12.0, 25.0, 34.0)
    return temperature, water, ph, solar


def interaction_features(memberships: tuple[float, float, float, float]) -> tuple[float, float]:
    """Factor the mechanistic fit into two transparent, non-target interactions."""
    temperature, water, ph, solar = memberships
    return temperature ** .42 * water ** .26, ph ** .18 * solar ** .14


def feature_row(
    profile: CropProfile,
    temperature_c: float,
    annual_precipitation_mm: float,
    soil_ph: float,
    solar_mj_m2_day: float,
    irrigated: bool,
    include_interactions: bool = True,
) -> list[float]:
    memberships = range_memberships(profile, temperature_c, annual_precipitation_mm, soil_ph, solar_mj_m2_day, irrigated)
    interactions = interaction_features(memberships) if include_interactions else ()
    return [temperature_c, annual_precipitation_mm, soil_ph, solar_mj_m2_day, float(irrigated), *profile.model_values(), *memberships, *interactions]


def teacher_scores(profile: CropProfile, temperature_c: float, annual_precipitation_mm: float, soil_ph: float, solar_mj_m2_day: float, irrigated: bool) -> dict[str, float]:
    temperature, water, ph, solar = range_memberships(profile, temperature_c, annual_precipitation_mm, soil_ph, solar_mj_m2_day, irrigated)
    suitability = 100.0 * math.prod([
        max(1e-6, temperature) ** 0.42,
        max(1e-6, water) ** 0.26,
        max(1e-6, ph) ** 0.18,
        max(1e-6, solar) ** 0.14,
    ])
    if min(temperature, water, ph, solar) == 0:
        suitability = 0.0
    return {
        "suitability": max(0.0, min(100.0, suitability)),
        "temperature": temperature * 100.0,
        "water": water * 100.0,
        "soil_ph": ph * 100.0,
        "solar": solar * 100.0,
    }
