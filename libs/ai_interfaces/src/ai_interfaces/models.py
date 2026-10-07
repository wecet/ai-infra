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

    dataset_path: Path
    output_path: Path
    mlflow_url: AnyHttpUrl | None = None
    project_id: str = Field(min_length=1)
    dataset_version_id: str = Field(min_length=1)
    class_names: tuple[str, ...] = Field(min_length=1)
    devices: tuple[str, ...] = ("cpu",)
    epochs: int = Field(default=10, ge=1)
    batch_size: int = Field(default=32, ge=1)
    learning_rate: float = Field(default=1e-3, gt=0)
    weight_decay: float = Field(default=0.0, ge=0)
    image_size: int = Field(default=224, ge=1)
    random_seed: int = 42
    validation_split: float = Field(default=0.2, ge=0, lt=1)


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
