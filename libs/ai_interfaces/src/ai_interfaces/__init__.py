"""Public, framework-neutral contracts for ai-infra model packages."""
from .models import (
    AnomalyModelConfig,
    AnomalyDetectionModel,
    BaseModelConfig,
    BaseVisionModel,
    DatasetVersion,
    ImageClassificationModel,
    ModelArtifact,
    ModelDescriptor,
    ObjectDetectionModel,
    TrainingContext,
    TrainingResult,
)

__all__ = [name for name in globals() if not name.startswith("_")]
