from __future__ import annotations

import argparse
import copy
import io
import json
import math
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from .features import COMPACT_FEATURE_NAMES, FEATURE_NAMES, feature_row, teacher_scores
from .bundle_validation import EXPECTED_MEMBERS, validate_bundle
from .inference import CLIMATE_HISTORY_END_YEAR, CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_YEARS, MAX_CLIMATE_HISTORY_YEARS, MONTHS, CropFitPredictor, align_model_features, sha256_file
from .profiles import resolve_profile
from .yield_atlas import aggregate_neighbor_prior, haversine_km, load_atlas, metric_summary, nearest_evidence


def climate(temperature: float) -> list[dict]:
    return [{
        "month": month,
        "temperatureC": temperature,
        "precipitationMmDay": 3.0,
        "solarMjM2Day": 18.0,
    } for month in MONTHS]


def verify(artifact: Path, profiles: Path) -> None:
    with tempfile.TemporaryDirectory() as bundle_directory:
        bundle_root = Path(bundle_directory)

        def archive(name: str, members: list[tuple[str, str]]) -> Path:
            path = bundle_root / name
            with tarfile.open(path, "w:gz") as bundle:
                for member_name, kind in members:
                    member = tarfile.TarInfo(member_name)
                    if kind == "file":
                        payload = b"test"
                        member.size = len(payload)
                        bundle.addfile(member, io.BytesIO(payload))
                    else:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "cropfit.joblib"
                        bundle.addfile(member)
            return path

        valid_members = [(name, "file") for name in sorted(EXPECTED_MEMBERS)]
        validate_bundle(archive("valid.tar.gz", valid_members))
        invalid_archives = (
            archive("duplicate.tar.gz", valid_members + [valid_members[0]]),
            archive("symlink.tar.gz", [(name, "link" if index == 0 else "file") for index, (name, _) in enumerate(valid_members)]),
            archive("traversal.tar.gz", valid_members[:-1] + [("../ecocrop.csv", "file")]),
        )
        for invalid_archive in invalid_archives:
            try:
                validate_bundle(invalid_archive)
            except ValueError:
                pass
            else:
                raise AssertionError(f"unsafe CropFit bundle was accepted: {invalid_archive.name}")

    actual = [0.0, 1.0]
    candidate_a = [0.10004, 0.89996]
    candidate_b = [0.10003, 0.89997]
    assert metric_summary(actual, candidate_a) == metric_summary(actual, candidate_b)
    assert metric_summary(actual, candidate_b, rounded=False)["maePercentile"] < metric_summary(
        actual, candidate_a, rounded=False,
    )["maePercentile"]

    assert (CLIMATE_HISTORY_START_YEAR, CLIMATE_HISTORY_END_YEAR, len(CLIMATE_HISTORY_YEARS)) == (2016, 2025, 10)
    predictor = CropFitPredictor(artifact, profiles)
    assert predictor.artifact_sha256 == sha256_file(artifact)
    assert len(predictor.artifact_sha256) == 64
    assert predictor.model.n_features_in_ == len(predictor.metadata["featureNames"]), "artifact and feature metadata disagree"
    expected_positions = [FEATURE_NAMES.index(name) for name in predictor.metadata["featureNames"]]
    assert predictor.model_features(list(range(len(FEATURE_NAMES)))) == expected_positions
    assert align_model_features(list(range(len(FEATURE_NAMES))), len(FEATURE_NAMES) - 2) == list(range(len(FEATURE_NAMES) - 2))
    assert align_model_features(
        list(range(len(FEATURE_NAMES))), len(COMPACT_FEATURE_NAMES), COMPACT_FEATURE_NAMES,
    ) == [FEATURE_NAMES.index(name) for name in COMPACT_FEATURE_NAMES]
    if predictor.metadata["model"].endswith(("v0.6", "v0.7", "v0.8", "v0.9", "v0.9.1", "v0.10.0", "v0.11.0")):
        assert predictor.metadata["selectedModel"] == "extraTrees"
    if predictor.metadata["model"].endswith(("v0.9", "v0.9.1")):
        assert predictor.metadata["modelParameters"]["nEstimators"] == 70
        assert predictor.metadata["trainingExamples"] == 151_800
        assert predictor.metadata["evaluationExamples"] == 134_064
    if predictor.metadata["model"].endswith("v0.10.0"):
        assert predictor.metadata["modelParameters"]["nEstimators"] == 40
        assert predictor.metadata["trainingExamples"] == 253_000
        assert predictor.metadata["evaluationExamples"] == 134_064
    if predictor.metadata["model"].endswith("v0.11.0"):
        assert predictor.metadata["modelParameters"]["nEstimators"] == 40
        assert predictor.metadata["modelParameters"]["inputFeatures"] == 6
        assert predictor.metadata["featureNames"] == COMPACT_FEATURE_NAMES
        assert predictor.metadata["trainingExamples"] == 253_000
        assert predictor.metadata["evaluationExamples"] == 134_064
        assert predictor.metadata["metrics"]["mae"] <= .02
        assert predictor.metadata["metrics"]["p90AbsoluteError"] <= .05
    if predictor.metadata["model"].endswith("v0.12.1"):
        assert predictor.metadata["selectedModel"] == "logLinear"
        assert predictor.metadata["modelParameters"]["estimator"] == "LogLinearCropFitRegressor"
        assert predictor.metadata["modelParameters"]["membershipFloor"] == 1e-6
        assert predictor.metadata["modelParameters"]["inputFeatures"] == 4
        assert predictor.metadata["featureNames"] == COMPACT_FEATURE_NAMES[:4]
        assert predictor.metadata["modelParameters"]["coefficients"] == {
            "temperature_range_fit": .42,
            "water_range_fit": .26,
            "ph_range_fit": .18,
            "solar_range_fit": .14,
        }
        assert predictor.metadata["metrics"]["maximumAbsoluteError"] <= 1e-5
    if predictor.metadata.get("promotionGate"):
        assert predictor.metadata["promotionGate"]["passed"]
        assert all(predictor.metadata["promotionGate"]["checks"].values())
    history = [climate(18.0 + offset) for offset in (-3, -2, -1, 0, 0, 1, 1, 2, 3, 5)]
    result = predictor.predict("tomato", 29.76, -95.37, 6.5, True, climate(20.0), history)
    assert result["plantingReliability"]["years"] == 10
    assert "2016–2025" in result["disclaimer"]
    calibration = predictor.metadata["uncertaintyCalibration"]
    if calibration.get("normalizedErrorQuantiles") or calibration.get("absoluteErrorQuantiles"):
        assert calibration["gate"]["passed"]
        assert result["confidence"] == calibration["nominalCoverage"]["p80"] == .8
        assert result["expectedAbsoluteError"]["p80"] <= result["expectedAbsoluteError"]["p90"]
    conditional = predictor.metadata.get("conditionalUncertaintyCalibration")
    if conditional:
        assert conditional["gate"]["passed"]
        assert .78 <= conditional["activeHeldOutCoverage"]["p80"] <= .82
        assert .88 <= conditional["activeHeldOutCoverage"]["p90"] <= .92
    assert result["bestReliablePlantingMonth"] in MONTHS
    assert len(result["monthlyCurve"]) == 12
    for month in result["monthlyCurve"]:
        assert month["historicalP10"] <= month["historicalMedian"] <= month["historicalP90"]
        assert 0 <= month["reliability"] <= 1

    profile = resolve_profile("tomato", predictor.profiles)
    interaction_row = feature_row(profile, 22, 900, 6.5, 18, True)
    interaction_target = teacher_scores(profile, 22, 900, 6.5, 18, True)["suitability"]
    assert abs(100 * interaction_row[-2] * interaction_row[-1] - interaction_target) < 1e-10
    ordinary = predictor.curve(profile, climate(20.0) + climate(20.0), 6.5, True)
    hot_next_year = predictor.curve(profile, climate(20.0) + climate(45.0), 6.5, True)
    assert ordinary[-1]["score"] != hot_next_year[-1]["score"], "late planting did not use following-year climate"
    scenarios = [climate(18.0), climate(20.0) + climate(21.0), climate(25.0)]
    assert predictor.curves(profile, scenarios, 6.5, True) == [predictor.curve(profile, values, 6.5, True) for values in scenarios]
    stress = climate((profile.temp_opt_min + profile.temp_opt_max) / 2)
    for item in stress:
        item["precipitationMmDay"] = ((profile.rain_opt_min + profile.rain_opt_max) / 2) / 365.25
        item["solarMjM2Day"] = 34.0
    _, stress_teacher, _, _ = predictor.curve_inputs(profile, stress, 6.5, False)
    stress_curve = predictor.curve(profile, stress, 6.5, False)
    assert all(item["score"] <= target["suitability"] for item, target in zip(stress_curve, stress_teacher, strict=True))
    assert all(item["score"] == 0 for item in stress_curve), "seasonal EcoCrop ceiling did not stop boundary extrapolation"
    assert all(item["expectedAbsoluteErrorP80"] == item["expectedAbsoluteErrorP90"] == 0 for item in stress_curve)
    onboarding_profiles = {
        "basil": "Ocimum basilicum",
        "kale": "Brassica oleracea var. acephala",
        "common bean": "Phaseolus vulgaris",
        "melon": "Cucumis melo",
        "onion": "Allium cepa",
        "sunflower": "Helianthus annuus",
        "silage corn": "Zea mays",
        "spring wheat": "Triticum aestivum",
    }
    for name, scientific_name in onboarding_profiles.items():
        assert resolve_profile(name, predictor.profiles).scientific_name == scientific_name

    invalid = climate(20.0) + climate(20.0)
    invalid[-1]["precipitationMmDay"] = -1
    try:
        predictor.curve(profile, invalid, 6.5, True)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid second-year climate was accepted")

    for invalid_arguments in (
        {"crop": "x", "latitude": 29.76, "longitude": -95.37},
        {"crop": "corn", "latitude": math.nan, "longitude": -95.37},
        {"crop": "corn", "latitude": 91, "longitude": -95.37},
        {"crop": "corn", "latitude": 29.76, "longitude": -181},
        {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "soil_ph": 11},
        {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "irrigated": 1},
        {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "climate_history": [climate(20.0)] * (MAX_CLIMATE_HISTORY_YEARS + 1)},
        {"crop": "corn", "latitude": 29.76, "longitude": -95.37, "climate_history": [climate(20.0)[:11]]},
    ):
        try:
            predictor.predict(climate=climate(20.0), **invalid_arguments)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid direct predictor request was accepted: {invalid_arguments}")

    with patch("cropfit.inference.joblib.load", return_value={"unexpected": True}):
        try:
            CropFitPredictor(artifact, profiles)
        except RuntimeError as error:
            assert "model and metadata" in str(error)
        else:
            raise AssertionError("malformed artifact contract was accepted")

    if predictor.metadata["model"].endswith("v0.12.1"):
        malformed_model = copy.deepcopy(predictor.model)
        del malformed_model.coef_
        with patch("cropfit.inference.joblib.load", return_value={
            "model": malformed_model,
            "metadata": predictor.metadata,
        }):
            try:
                CropFitPredictor(artifact, profiles)
            except RuntimeError as error:
                assert "supported fitted estimator" in str(error)
            else:
                raise AssertionError("unfitted log-linear artifact was accepted")

    atlas = artifact.parents[1] / "evaluation/yield-atlas-v11.json"
    if atlas.exists():
        atlas_report = load_atlas(str(atlas.resolve()))
        assert atlas_report["name"] == "USDA county yield atlas v11"
        assert atlas_report["years"] == list(range(2010, 2026))
        assert atlas_report["historyWindowComparison"]["gate"]["passed"]
        assert atlas_report["uncertaintyValidation"]["gate"]["passed"]
        assert atlas_report["spatialTransferValidation"]["gate"]["passed"]
        assert atlas_report["spatialTransferValidation"]["productionBlend"]["gate"]["passed"]
        production_blend = atlas_report["spatialTransferValidation"]["productionBlend"]
        expected_crop_weights = {
            "corn": {"Northeast": 0.0, "Midwest": .15, "South": .15, "West": 0.0},
            "soybean": {"Northeast": 0.0, "Midwest": .15, "South": .15, "West": 0.0},
            "wheat": {"Northeast": 0.0, "Midwest": .2, "South": .2, "West": 0.0},
        }
        assert production_blend["selectedWeights"]["regionalNeighborhoodByCropRegion"] == expected_crop_weights
        stability_veto = {item["crop"]: item["enabled"] for item in production_blend["cropStabilityVeto"]}
        assert stability_veto == {"corn": False, "soybean": False, "wheat": True}
        assert all(
            item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0
            for item in (*production_blend["perRegionConfirmation"], *production_blend["perRegionFinalSignal"])
        )
        evidence = nearest_evidence("corn", 29.7604, -95.3698, atlas)
        assert evidence and evidence["county"] == "Fort Bend County" and evidence["observations"] == 14
        assert evidence["latest"]["year"] == 2025
        assert [item["year"] for item in evidence["history"]][-3:] == [2023, 2024, 2025]
        expected = evidence["observedYieldPrior"]["expectedPercentile"]
        assert evidence["observedYieldPrior"]["interval80"][0] <= expected <= evidence["observedYieldPrior"]["interval80"][1]
        assert evidence["observedYieldPrior"]["intervalMethod"] == "local-regional-blend-conformal"
        calibration = atlas_report["spatialTransferValidation"]["productionBlend"]["intervalCalibration"]
        assert calibration["meanWidth90Reduction"] >= .06
        assert calibration["selectedShrinkage"] == .4
        assert calibration["championV10MeanWidth90Reduction"] >= .025
        assert calibration["productionBlendRadii"] == {
            "observations": 26563, "coverage80": .8304, "coverage90": .9226,
            "meanWidth80": .3821, "meanWidth90": .4969,
        }
        assert calibration["selectedCropRegionalScales"]["corn"]["South"] == {
            "scale80": .96, "scale90": .98,
        }
        assert .88 <= calibration["productionBlendRadii"]["coverage90"] <= .94
        assert calibration["selectedRegionalScales"] == {
            "Northeast": {"scale80": 1.05, "scale90": 1.0},
            "Midwest": {"scale80": 1.0, "scale90": 1.0},
            "South": {"scale80": 1.0, "scale90": 1.0},
            "West": {"scale80": 1.45, "scale90": 1.45},
        }
        assert all(.85 <= item["coverage90"] <= .98 for item in calibration["perRegionFinal"])
        assert evidence["observedYieldPrior"]["distanceBucket"] == "25-50"
        assert 1 <= evidence["observedYieldPrior"]["neighborCount"] <= 9
        assert len(evidence["regionalNeighbors"]) == evidence["observedYieldPrior"]["neighborCount"] == 6
        assert evidence["regionalNeighbors"][0]["weight"] == .85
        corn_calibration = next(item for item in calibration["groups"] if (
            item["crop"] == "corn"
            and item["historyBucket"] == evidence["observedYieldPrior"]["effectiveHistoryBucket"]
        ))
        reported_expected = evidence["observedYieldPrior"]["expectedPercentile"]
        assert evidence["observedYieldPrior"]["interval90"] == [
            round(max(0.0, reported_expected - corn_calibration["absoluteErrorP90"] * .98), 4),
            round(min(1.0, reported_expected + corn_calibration["absoluteErrorP90"] * .98), 4),
        ]
        wheat_evidence = nearest_evidence("wheat", 46.8, -100.8, atlas)
        assert wheat_evidence and wheat_evidence["state"] == "ND"
        assert wheat_evidence["observedYieldPrior"]["intervalMethod"] == "local-regional-blend-conformal"
        assert wheat_evidence["regionalNeighbors"][0]["weight"] == .8
        assert abs(sum(item["weight"] for item in wheat_evidence["regionalNeighbors"]) - 1) < .0001

    production_blend_v2_validation = artifact.parents[1] / "evaluation/production-blend-v2-validation-v10.json"
    if production_blend_v2_validation.exists():
        blend_report = json.loads(production_blend_v2_validation.read_text())
        assert blend_report["gate"] == {"passed": True, "pointPassed": True, "intervalPassed": True}
        assert blend_report["final"]["spearmanGain"] > 0
        assert blend_report["final"]["maeReduction"] > 0
        assert blend_report["final"]["spearmanGainBootstrap95"][0] > 0
        assert [
            item["crop"] for item in blend_report["selection"]["stabilityVeto"] if item["enabled"]
        ] == ["wheat"]
        assert all(item["spearmanGain"] >= 0 and item["maeReduction"] >= 0 for item in blend_report["perYearFinal"])

    interval_scaling_validation = artifact.parents[1] / "evaluation/interval-scaling-validation-v11-candidate.json"
    if interval_scaling_validation.exists():
        interval_report = json.loads(interval_scaling_validation.read_text())
        assert not interval_report["gate"]["passed"]
        assert interval_report["gate"]["checks"]["pooledWidthReductionAtLeast4Percent"]
        assert not interval_report["gate"]["checks"]["regionalFinal"]
        assert interval_report["meanWidth90Reduction"] >= .04
        western_final = next(item for item in interval_report["perRegionFinal"] if item["region"] == "West")
        assert western_final["coverage90"] > .98
        assert interval_report["decision"] == "reject; retain atlas v10 regional interval scales"

    interval_shrinkage_validation = artifact.parents[1] / "evaluation/interval-shrinkage-validation-v11.json"
    if interval_shrinkage_validation.exists():
        shrinkage_report = json.loads(interval_shrinkage_validation.read_text())
        assert shrinkage_report["gate"]["passed"]
        assert shrinkage_report["selectedShrinkage"] == .4
        assert shrinkage_report["meanWidth90Reduction"] >= .025
        assert shrinkage_report["selectedCropRegionalScales"] == calibration["selectedCropRegionalScales"]
        assert shrinkage_report["candidate"] == calibration["productionBlendRadii"]

    asymmetric_interval_development = artifact.parents[1] / "evaluation/asymmetric-interval-development-v12.json"
    if asymmetric_interval_development.exists():
        asymmetric_report = json.loads(asymmetric_interval_development.read_text())
        assert not asymmetric_report["gate"]["passed"]
        assert asymmetric_report["protocol"]["finalYearsOpenedForDecision"] == []
        assert asymmetric_report["protocol"]["lowerTailShareCandidates"] == [.1, .25, .4, .5, .6, .75, .9]
        assert asymmetric_report["gate"]["checks"]["atLeastOneCandidatePassesCoverage"]
        assert not asymmetric_report["gate"]["checks"]["atLeastOneCandidateAdvances"]
        assert asymmetric_report["selectedCandidate"] is None
        assert asymmetric_report["decision"] == "reject asymmetric intervals; retain atlas v11"

    trend_validation = artifact.parents[1] / "evaluation/trend-validation-v1.json"
    if trend_validation.exists():
        trend_report = json.loads(trend_validation.read_text())
        assert not trend_report["gate"]["passed"]
        assert trend_report["protocol"]["enabledCrops"] == ["corn", "soybean"]
        assert trend_report["confirmation"]["spearmanDelta"] < 0
        assert trend_report["confirmation"]["maeDelta"] > 0
        assert trend_report["final"]["spearmanDeltaBootstrap95"][1] < 0
        assert next(item for item in trend_report["final"]["perCrop"] if item["crop"] == "wheat")["spearmanDelta"] == 0

    inference_benchmark = artifact.parents[1] / "evaluation/inference-benchmark-v5.json"
    if inference_benchmark.exists():
        benchmark = json.loads(inference_benchmark.read_text())
        assert benchmark["gate"]["passed"]
        assert benchmark["production"]["artifactSha256"] == predictor.artifact_sha256
        assert benchmark["production"]["outputsIdentical"]
        assert benchmark["championV011"]["artifactSha256"] == "96fedbe3ca60c3eb61495e5d5c288696597ee4340f4451f4517516403982c508"
        assert benchmark["championV011"]["outputsIdentical"]
        assert benchmark["productionVsChampion"]["batchedSpeedup"] > 1
        assert benchmark["productionVsChampion"]["artifactSizeReductionPercent"] > 99

    if atlas.exists():
        assert evidence["observedYieldPrior"]["expectedPercentile"] != evidence["regionalNeighbors"][0]["expectedPercentile"]
        assert abs(sum(item["weight"] for item in evidence["regionalNeighbors"]) - 1) < .0001
        western_evidence = nearest_evidence("wheat", 39.7392, -104.9903, atlas)
        assert western_evidence and western_evidence["state"] == "CO"
        assert western_evidence["observedYieldPrior"]["neighborCount"] == 1
        assert western_evidence["observedYieldPrior"]["intervalMethod"] == "region-gated-local-conformal"
        assert western_evidence["regionalNeighbors"][0]["weight"] == 1.0
        assert atlas_report["predictionMethod"] == {"name": "shrunken exponential recency prior", "forecastYear": 2026, "halfLifeYears": 3.0, "recencyWeight": .8, "longHistoryWeight": .2}
        assert evidence["observedYieldPrior"]["interval90"][0] <= evidence["observedYieldPrior"]["interval80"][0]
        assert evidence["observedYieldPrior"]["interval90"][1] >= evidence["observedYieldPrior"]["interval80"][1]
        assert nearest_evidence("tomato", 29.7604, -95.3698, atlas) is None
        for crop, latitude, longitude in (("corn", 40.1, -88.2), ("soybean", 35.5, -90.4), ("wheat", 46.8, -100.8)):
            indexed = nearest_evidence(crop, latitude, longitude, atlas, max_distance_km=10_000)
            brute = min(
                (record for record in atlas_report["records"] if record["crop"] == crop),
                key=lambda record: haversine_km(latitude, longitude, record["latitude"], record["longitude"]),
            )
            assert indexed and indexed["fips"] == brute["fips"], f"spatial index changed nearest county for {crop}"

    subtype_atlas = artifact.parents[1] / "evaluation/yield-atlas-subtypes-v1.json"
    if subtype_atlas.exists():
        synthetic_neighbors = [
            {"distanceKm": 10.0, "prediction": .2, "historyCount": 1},
            {"distanceKm": 10.0, "prediction": .8, "historyCount": 4},
        ]
        distance_only = aggregate_neighbor_prior(synthetic_neighbors, 2, 1.0)
        history_weighted = aggregate_neighbor_prior(synthetic_neighbors, 2, 1.0, 1.0)
        assert distance_only[0] == .5 and distance_only[3] == [.5, .5]
        assert math.isclose(history_weighted[0], .68) and history_weighted[3] == [.2, .8]
        subtype_report = load_atlas(str(subtype_atlas.resolve()))
        assert subtype_report["crops"] == ["silage corn", "spring wheat"]
        assert subtype_report["validation"]["gate"]["passed"]
        assert subtype_report["validation"]["selectedRecencyWeights"] == {
            "silage corn": .25, "spring wheat": .8,
        }
        assert subtype_report["validation"]["selectedCalibrationScopes"] == {
            "silage corn": "pooled", "spring wheat": "region-conditioned",
        }
        expected_history_depth = {
            "silage corn": {"region": "Midwest", "beta": -.02},
            "spring wheat": {"region": "West", "beta": -.02},
        }
        assert subtype_report["validation"]["selectedHistoryDepth"] == expected_history_depth
        assert subtype_report["spatialTransferValidation"]["selectedHistoryDepthByCrop"] == expected_history_depth
        assert subtype_report["predictionMethod"] == {
            "name": "crop-specific shrunken exponential recency prior",
            "forecastYear": 2026, "halfLifeYears": 3.0, "defaultRecencyWeight": .8,
            "recencyWeightByCrop": {"silage corn": .25, "spring wheat": .8},
        }
        silage_validation = next(
            item for item in subtype_report["validation"]["perCrop"]
            if item["crop"] == "silage corn"
        )
        assert silage_validation["temporalComparison"]["final"]["spearmanGain"] > 0
        assert silage_validation["temporalComparison"]["final"]["maeReduction"] > 0
        assert silage_validation["temporalComparison"]["finalSpearmanGainBootstrap95"][0] > 0
        spring = nearest_evidence("spring wheat", 46.8, -100.8, subtype_atlas)
        silage = nearest_evidence("silage corn", 43.0, -89.0, subtype_atlas)
        assert spring and spring["yieldUnit"] == "bu/acre" and spring["history"][0]["yieldPerAcre"] > 0
        assert silage and silage["yieldUnit"] == "tons/acre" and silage["history"][0]["yieldPerAcre"] > 0
        assert spring["observedYieldPrior"]["intervalMethod"] == "region-conditioned-disagreement-scaled-spatial-conformal"
        assert spring["observedYieldPrior"]["disagreementAlpha"] == 5.0
        assert spring["observedYieldPrior"]["calibrationRegion"] == "Midwest"
        assert spring["observedYieldPrior"]["neighborDisagreement"] >= 0
        assert silage["observedYieldPrior"]["intervalMethod"] == "history-scaled-spatial-neighborhood-conformal"
        assert silage["observedYieldPrior"]["calibrationRegion"] == "all"
        assert spring["observedYieldPrior"]["historyDepthRegion"] == "West"
        assert spring["observedYieldPrior"]["historyDepthFactor"] == 1.0
        assert silage["observedYieldPrior"]["historyDepthRegion"] == "Midwest"
        assert silage["observedYieldPrior"]["historyDepthBeta"] == -.02
        assert silage["observedYieldPrior"]["historyDepthFactor"] != 1.0
        assert spring["observedYieldPrior"]["neighborCount"] == 5
        assert silage["observedYieldPrior"]["neighborCount"] == 5
        assert abs(sum(item["weight"] for item in spring["regionalNeighbors"]) - 1) < .0001
        assert abs(sum(item["weight"] for item in silage["regionalNeighbors"]) - 1) < .0001

    ranking_validation = artifact.parents[1] / "evaluation/ranking-validation-v1.json"
    if ranking_validation.exists():
        ranking_report = json.loads(ranking_validation.read_text())
        assert not ranking_report["blendGate"]["passed"]
        assert ranking_report["productionGate"]["passed"]
        assert ranking_report["priorVsClimateFinalTest"]["priorAdvantageBootstrap95"][0] > 0

    recency_validation = artifact.parents[1] / "evaluation/recency-validation-v2.json"
    if recency_validation.exists():
        recency_report = json.loads(recency_validation.read_text())
        assert recency_report["selectedHalfLifeYears"] == 3
        assert recency_report["selectedRecencyWeight"] == .8
        assert recency_report["gate"]["passed"]
        assert recency_report["finalTest"]["spearmanDeltaBootstrap95"][0] > 0
        assert all(item["spearmanDelta"] >= 0 and item["maeDelta"] <= 0 for item in recency_report["perYearFinalTest"])

    uncertainty_validation = artifact.parents[1] / "evaluation/uncertainty-validation-v0.5.1.json"
    if uncertainty_validation.exists():
        uncertainty_report = json.loads(uncertainty_validation.read_text())
        assert uncertainty_report["gate"]["passed"]
        assert uncertainty_report["robustness"]["gate"]["passed"]
        assert uncertainty_report["robustness"]["summary"]["wins"] == uncertainty_report["robustness"]["summary"]["seeds"] == 5

    estimator_validation = artifact.parents[1] / "evaluation/estimator-validation-v0.6.json"
    if estimator_validation.exists():
        estimator_report = json.loads(estimator_validation.read_text())
        assert estimator_report["gate"]["passed"]
        assert estimator_report["summary"]["lockedSeedWins"] == estimator_report["summary"]["lockedSeeds"] == 7
        assert estimator_report["summary"]["finalMeanMaeImprovementPercent"] >= 30

    capacity_validation = artifact.parents[1] / "evaluation/capacity-validation-v0.7.json"
    if capacity_validation.exists():
        capacity_report = json.loads(capacity_validation.read_text())
        assert capacity_report["gate"]["passed"]
        assert capacity_report["summary"]["lockedSeedWins"] == capacity_report["summary"]["lockedSeeds"] == 7
        assert capacity_report["summary"]["lockedMeanMaeImprovementPercent"] >= 2
        assert capacity_report["summary"]["lockedMeanP90ImprovementPercent"] >= 1
        assert capacity_report["summary"]["candidateSerializedSizeBytes"] <= 130_000_000

    interaction_validation = artifact.parents[1] / "evaluation/interaction-validation-v0.8.json"
    if interaction_validation.exists():
        interaction_report = json.loads(interaction_validation.read_text())
        assert interaction_report["gate"]["passed"]
        assert interaction_report["summary"]["lockedSeedWins"] == interaction_report["summary"]["lockedSeeds"] == 7
        assert interaction_report["summary"]["lockedMeanMaeImprovementPercent"] >= 70
        assert interaction_report["summary"]["lockedMeanP90ImprovementPercent"] >= 70
        assert interaction_report["summary"]["candidateSerializedSizeBytes"] <= 80_000_000

    density_validation = artifact.parents[1] / "evaluation/training-density-validation-v0.9.json"
    if density_validation.exists():
        density_report = json.loads(density_validation.read_text())
        assert density_report["gate"]["passed"]
        assert density_report["summary"]["lockedSeedWins"] == density_report["summary"]["lockedSeeds"] == 7
        assert density_report["summary"]["lockedMeanMaeImprovementPercent"] >= 10
        assert density_report["summary"]["lockedMeanP90ImprovementPercent"] >= 10
        assert density_report["summary"]["candidateSerializedSizeBytes"] <= 72_000_000
        assert density_report["protocol"]["fixedEvaluation"].startswith("Both models use identical")

    refinement_validation = artifact.parents[1] / "evaluation/density-refinement-validation-v0.10.json"
    if refinement_validation.exists():
        refinement_report = json.loads(refinement_validation.read_text())
        assert refinement_report["gate"]["passed"]
        assert refinement_report["summary"]["lockedSeedWins"] == refinement_report["summary"]["lockedSeeds"] == 7
        assert refinement_report["summary"]["lockedMeanMaeImprovementPercent"] >= 10
        assert refinement_report["summary"]["lockedMeanP90ImprovementPercent"] >= 10
        assert refinement_report["summary"]["candidateSerializedSizeBytes"] < refinement_report["summary"]["championSerializedSizeBytes"]

    density_shift_validation = artifact.parents[1] / "evaluation/density-shift-validation-v0.10.json"
    if density_shift_validation.exists():
        density_shift_report = json.loads(density_shift_validation.read_text())
        assert not density_shift_report["gate"]["passed"]
        assert density_shift_report["gains"]["deployedMaePercent"] < 0
        assert density_shift_report["protocol"]["candidate"].startswith("v0.10 candidate")

    refinement_v2_validation = artifact.parents[1] / "evaluation/density-refinement-v2-validation-v0.10.json"
    if refinement_v2_validation.exists():
        refinement_v2_report = json.loads(refinement_v2_validation.read_text())
        assert refinement_v2_report["gate"]["passed"]
        assert refinement_v2_report["summary"]["seedWins"] == refinement_v2_report["summary"]["seeds"] == 10
        assert refinement_v2_report["summary"]["finalMeanMaeImprovementPercent"] >= 5
        assert refinement_v2_report["summary"]["finalMeanP90ImprovementPercent"] >= 5
        assert refinement_v2_report["independentShift"]["passed"]
        assert min(refinement_v2_report["independentShift"]["gains"].values()) >= 5

    shift_validation = artifact.parents[1] / "evaluation/scenario-shift-validation-v0.9.1.json"
    if shift_validation.exists():
        shift_report = json.loads(shift_validation.read_text())
        assert shift_report["gate"]["passed"]
        assert min(shift_report["gains"].values()) >= 10
        assert .78 <= shift_report["activeCoverage"]["conditionalMethodOnShifted"]["p80"] <= .82
        assert .88 <= shift_report["activeCoverage"]["conditionalMethodOnShifted"]["p90"] <= .92
        assert shift_report["activeCoverage"]["oldGlobalMethodOnShifted"]["p90"] < .7

    compact_validation = artifact.parents[1] / "evaluation/compact-validation-v1.json"
    if compact_validation.exists():
        compact_report = json.loads(compact_validation.read_text())
        assert not compact_report["gate"]["passed"]
        assert compact_report["summary"]["seedWins"] == 0
        assert compact_report["summary"]["decision"].startswith("reject")

    ood_validation = artifact.parents[1] / "evaluation/ood-validation-v0.9.1.json"
    if ood_validation.exists():
        ood_report = json.loads(ood_validation.read_text())
        assert ood_report["gate"]["passed"]
        assert ood_report["heldOut"]["errorNeverIncreased"]
        assert ood_report["heldOut"]["seasonalCeiling"]["mae"] < ood_report["heldOut"]["rawSurrogate"]["mae"]

    current_ood_validation = artifact.parents[1] / "evaluation/ood-validation-v0.10.0.json"
    if current_ood_validation.exists():
        current_ood_report = json.loads(current_ood_validation.read_text())
        assert current_ood_report["model"].endswith("v0.10.0")
        assert current_ood_report["gate"]["passed"]
        assert current_ood_report["heldOut"]["errorNeverIncreased"]
        assert current_ood_report["heldOut"]["seasonalCeiling"]["mae"] < .006

    feature_compaction_validation = artifact.parents[1] / "evaluation/feature-compaction-v2-validation-v0.11.json"
    if feature_compaction_validation.exists():
        feature_compaction_report = json.loads(feature_compaction_validation.read_text())
        assert feature_compaction_report["gate"]["passed"]
        assert feature_compaction_report["summary"]["seedWins"] == feature_compaction_report["summary"]["seeds"] == 10
        assert feature_compaction_report["summary"]["allMeanMaeImprovementPercent"] >= 20
        assert feature_compaction_report["summary"]["allMeanP90ImprovementPercent"] >= 20
        assert feature_compaction_report["summary"]["compactSerializedSizeBytes"] <= 64_000_000
        assert feature_compaction_report["independentShift"]["passed"]

    compact_ood_validation = artifact.parents[1] / "evaluation/ood-validation-v0.11.0.json"
    if compact_ood_validation.exists():
        compact_ood_report = json.loads(compact_ood_validation.read_text())
        assert compact_ood_report["model"].endswith("v0.11.0")
        assert compact_ood_report["gate"]["passed"]
        assert compact_ood_report["heldOut"]["rawSurrogate"]["mae"] <= .011
        assert compact_ood_report["heldOut"]["seasonalCeiling"]["mae"] <= .004

    interaction_compaction_validation = artifact.parents[1] / "evaluation/interaction-compaction-validation-v0.12.json"
    if interaction_compaction_validation.exists():
        interaction_report = json.loads(interaction_compaction_validation.read_text())
        assert not interaction_report["gate"]["passed"]
        assert interaction_report["summary"]["seedWins"] == 9
        assert interaction_report["summary"]["seeds"] == 10
        failed = [item for item in interaction_report["results"] if not item["passedPerSeedGate"]]
        assert [item["seed"] for item in failed] == [20270218]
        assert failed[0]["interactionCandidate"]["deployedMaximumAbsoluteError"] > failed[0]["championV011"]["deployedMaximumAbsoluteError"]
        assert interaction_report["independentShift"]["passed"]

    leaf_smoothing_validation = artifact.parents[1] / "evaluation/leaf-smoothing-validation-v0.12.json"
    if leaf_smoothing_validation.exists():
        smoothing_report = json.loads(leaf_smoothing_validation.read_text())
        assert not smoothing_report["gate"]["passed"]
        assert smoothing_report["summary"]["seedWins"] == 4
        assert smoothing_report["summary"]["seeds"] == 10
        assert not smoothing_report["independentShift"]["passed"]
        assert smoothing_report["independentShift"]["gains"]["p90Percent"] < 5
        assert smoothing_report["independentShift"]["interactionCandidate"]["deployedMaximumAbsoluteError"] > smoothing_report["independentShift"]["championV011"]["deployedMaximumAbsoluteError"]

    density_refinement_v3_validation = artifact.parents[1] / "evaluation/density-refinement-v3-validation-v0.12.json"
    if density_refinement_v3_validation.exists():
        density_v3_report = json.loads(density_refinement_v3_validation.read_text())
        assert not density_v3_report["gate"]["passed"]
        assert density_v3_report["summary"]["seedWins"] == 5
        assert density_v3_report["summary"]["seeds"] == 10
        assert density_v3_report["summary"]["finalMeanP90ImprovementPercent"] < 5
        assert density_v3_report["summary"]["candidateSerializedSizeBytes"] > density_v3_report["summary"]["championSerializedSizeBytes"]
        assert density_v3_report["summary"]["candidateSerializedSizeBytes"] <= 70_000_000
        assert not density_v3_report["independentShift"]["passed"]
        assert density_v3_report["independentShift"]["gains"]["deployedMaePercent"] < 0
        failed_tails = [
            item for item in density_v3_report["results"]
            if item["interactionCandidate"]["deployedMaximumAbsoluteError"]
            > item["championV011"]["deployedMaximumAbsoluteError"]
        ]
        assert [item["seed"] for item in failed_tails] == [20270321, 20270322, 20270323, 20270328]

    density_capacity_development = artifact.parents[1] / "evaluation/density-capacity-development-v0.12.json"
    if density_capacity_development.exists():
        development_report = json.loads(density_capacity_development.read_text())
        assert development_report["protocol"]["reservedSeedsOpened"] is False
        assert development_report["advancedCandidates"] == []
        development_summary = {
            item["candidate"]: item for item in development_report["summary"]
        }
        densest = development_summary["300x32"]
        assert densest["meanMaeImprovementPercent"] >= 10
        assert densest["meanP90ImprovementPercent"] >= 10
        assert densest["seedScreensPassed"] == 2
        assert not densest["advanced"]
        for name in ("200x40-poisson", "200x48-poisson", "240x40-poisson"):
            assert development_summary[name]["seedScreensPassed"] == 0
            assert not development_summary[name]["advanced"]
        assert min(
            item["meanMaeImprovementPercent"]
            for name, item in development_summary.items()
            if "-q" in name
        ) < -100

    from .trained_api import PredictionRequest, predict as api_predict

    valid_climate = climate(20.0)
    PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, climate=valid_climate, climateHistory=[valid_climate] * 10)
    for invalid in (
        {"climate": valid_climate[:11]},
        {"climateHistory": [valid_climate] * 21},
        {"climateHistory": [valid_climate[:11]]},
        {"irrigated": 1},
    ):
        try:
            PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, **invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"unbounded or malformed climate request was accepted: {invalid.keys()}")

    class InvalidClimatePredictor:
        @staticmethod
        def predict(*_args, **_kwargs):
            raise ValueError("invalid climate")

    with patch("cropfit.trained_api.predictor", return_value=InvalidClimatePredictor()):
        try:
            api_predict(PredictionRequest(crop="corn", latitude=29.76, longitude=-95.37, climate=valid_climate))
        except HTTPException as error:
            assert error.status_code == 422
        else:
            raise AssertionError("invalid caller climate was not mapped to HTTP 422")

    print(
        f"CropFit inference verified: {predictor.metadata['model']} "
        f"({predictor.model.n_features_in_} selected of {len(FEATURE_NAMES)} engineered features, "
        "batched 10-year reliability, county evidence)"
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=root / "artifacts/cropfit.joblib")
    parser.add_argument("--profiles", type=Path, default=root / "data/raw/ecocrop.csv")
    args = parser.parse_args()
    verify(args.artifact, args.profiles)


if __name__ == "__main__":
    main()
