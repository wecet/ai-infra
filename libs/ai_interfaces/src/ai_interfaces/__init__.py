"""Public, framework-neutral contracts for ai-infra model packages."""
from .analysis import (
    EMBEDDING_TASK,
    SAMPLE_SELECTION_TASK,
    EmbeddingConfig,
    EmbeddingContext,
    EmbeddingResult,
    EmbeddingSet,
    EmbeddingWorkbench,
    SampleSelector,
    SampleSuggestion,
    SelectionConfig,
    SelectionContext,
    SelectionResult,
    validate_selection,
)
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
