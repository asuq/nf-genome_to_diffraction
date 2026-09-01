"""Integrity-checked coordinate and processed-model registry adapters."""

from genome_to_diffraction.model_registry.all_eligible import (
    AllEligibleModelEntry,
    AllEligibleModelLookupResult,
    AllEligibleModelRegistry,
    AllEligibleModelRegistryError,
    AllEligibleModelRegistryManifest,
    AllEligibleModelRegistryOutput,
    ModelUnavailableReason,
    SequenceGroupModelInventory,
    ValidatedProcessedModelInput,
    build_all_eligible_model_registry,
    load_all_eligible_model_registry,
)
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
    "AllEligibleModelEntry",
    "AllEligibleModelLookupResult",
    "AllEligibleModelRegistry",
    "AllEligibleModelRegistryError",
    "AllEligibleModelRegistryManifest",
    "AllEligibleModelRegistryOutput",
    "ExperimentalModelInputError",
    "ExperimentalModelParseError",
    "ExperimentalModelPreparationOutput",
    "ExperimentalModelPreparationRequest",
    "ModelUnavailableReason",
    "PredictedModelInputError",
    "PredictedModelParseError",
    "PredictedModelPreparationOutput",
    "PredictedModelPreparationRequest",
    "PredictedModelToolError",
    "SequenceGroupModelInventory",
    "ValidatedProcessedModelInput",
    "build_all_eligible_model_registry",
    "load_all_eligible_model_registry",
    "prepare_experimental_models",
    "prepare_predicted_models",
]
