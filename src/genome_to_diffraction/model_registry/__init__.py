"""Integrity-checked coordinate and processed-model registry adapters."""

from genome_to_diffraction.model_registry.experimental import (
    ExperimentalModelInputError,
    ExperimentalModelParseError,
    ExperimentalModelPreparationOutput,
    ExperimentalModelPreparationRequest,
    prepare_experimental_models,
)
from genome_to_diffraction.model_registry.predicted import (
    PredictedModelInputError,
    PredictedModelParseError,
    PredictedModelPreparationOutput,
    PredictedModelPreparationRequest,
    PredictedModelToolError,
    prepare_predicted_models,
)

__all__ = [
    "ExperimentalModelInputError",
    "ExperimentalModelParseError",
    "ExperimentalModelPreparationOutput",
    "ExperimentalModelPreparationRequest",
    "PredictedModelInputError",
    "PredictedModelParseError",
    "PredictedModelPreparationOutput",
    "PredictedModelPreparationRequest",
    "PredictedModelToolError",
    "prepare_experimental_models",
    "prepare_predicted_models",
]
