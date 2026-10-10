"""The compatibility boundary every model package must implement.

The interfaces deliberately avoid torch/tensorflow types. Implementations may use any
framework internally while the infrastructure can configure, train and package them in
one predictable way.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Generic, Mapping, Sequence, TypeVar

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class BaseModelConfig(BaseModel):
    """Shared, serialisable configuration for every training implementation.

    Implementations subclass this model to add architecture-specific fields. Keeping
    ``extra='forbid'`` makes misspelled or unsupported parameters a validation error.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    dataset_path: Path = Field(description="Path to the immutable dataset archive used for this run. AI Studio fills this from the published dataset version.")
    output_path: Path = Field(description="Directory for model artifacts and training logs. The compute agent assigns a separate directory for each run.")
    mlflow_url: AnyHttpUrl | None = Field(default=None, description="MLflow tracking server URL for recording run metrics and artifacts. AI Studio supplies this infrastructure setting.")
    project_id: str = Field(min_length=1, description="Identifier of the AI Studio project that owns this training run.")
    dataset_version_id: str = Field(min_length=1, description="Identifier of the frozen dataset version used for reproducible training.")
    class_names: tuple[str, ...] = Field(min_length=1, description="Ordered class names from the published dataset. Their order determines the model output label mapping.")
    devices: tuple[str, ...] = Field(default=("cpu",), description="Requested compute devices: cpu or gpu. Availability depends on the compute agent and model implementation.")
    epochs: int = Field(default=10, ge=1, description="Number of complete passes through the training data.")
    batch_size: int = Field(default=32, ge=1, description="Number of training images processed together in each optimizer step. Larger batches require more memory.")
    learning_rate: float = Field(default=1e-3, gt=0, description="Optimizer step size controlling how much model weights change during training. Lower values make smaller updates.")
    weight_decay: float = Field(default=0.0, ge=0, description="Optimizer penalty on large weights to help limit overfitting. Set to 0 to disable weight decay.")
    image_size: int = Field(default=224, ge=1, description="Target image size in pixels. The model implementation determines how images are resized.")
    random_seed: int = Field(default=42, description="Seed used for model initialization, dataset splitting, shuffling and random augmentations. Reusing it helps reproduce runs; exact results can still vary across devices.")
    validation_split: float = Field(default=0.2, ge=0, lt=1, description="Fraction of images held out for validation loss rather than optimizer updates. For example, 0.2 requests 20 percent; set to 0 to disable validation. Small datasets may limit the holdout size.")


@dataclass(frozen=True)
class ModelDescriptor:
    key: str
    name: str
    task: str
    description: str
    defaults: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetVersion:
    project_id: str
    version_id: str
    name: str
    annotation_type: str
    archive: Path
    classes: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class TrainingContext:
    job_id: str
    dataset: DatasetVersion
    output_dir: Path
    hyperparameters: Mapping[str, Any]
    devices: tuple[str, ...] = ("cpu",)


@dataclass(frozen=True)
class ModelArtifact:
    path: Path
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class TrainingResult:
    metrics: Mapping[str, float]
    artifact: ModelArtifact
    summary: str = ""


ConfigT = TypeVar("ConfigT", bound=BaseModelConfig)


class BaseVisionModel(ABC, Generic[ConfigT]):
    """Common lifecycle required by local and remote training agents."""

    config_type: ClassVar[type[BaseModelConfig]]

    def __init__(self, config: ConfigT | Mapping[str, Any]):
        config_type = getattr(type(self), "config_type", None)
        if not isinstance(config_type, type) or not issubclass(config_type, BaseModelConfig):
            raise TypeError(f"{type(self).__name__} must declare config_type as a BaseModelConfig subclass")
        self.config: ConfigT = (config if isinstance(config, config_type)
                                else config_type.model_validate(config))

    @classmethod
    @abstractmethod
    def descriptor(cls) -> ModelDescriptor:
        """Describe the selectable model and its default hyperparameters."""

    @abstractmethod
    def train(self, context: TrainingContext) -> TrainingResult:
        """Train from an immutable dataset archive and return a portable artifact."""

    @abstractmethod
    def load(self, artifact: Path) -> None:
        """Load a previously saved artifact for inference."""

    @abstractmethod
    def predict(self, image: Path) -> Sequence[Mapping[str, Any]]:
        """Return JSON-serialisable predictions."""


class ImageClassificationModel(BaseVisionModel[ConfigT], ABC):
    """Required base class for image-classification implementations."""


class ObjectDetectionModel(BaseVisionModel[ConfigT], ABC):
    """Required base class for object-detection implementations."""
