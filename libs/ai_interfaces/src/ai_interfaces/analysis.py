"""Dataset-analysis contracts: embedding workbenches and sample selectors.

These sit beside the training contracts in ``models.py``. They follow the same rules:
no framework types cross the boundary, configuration is a strict Pydantic model, and
large outputs (embedding matrices) travel as files rather than in memory.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, ClassVar, Generic, Literal, Mapping, Sequence, TypeVar

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from .models import DatasetVersion, ModelDescriptor

EMBEDDING_TASK = "embedding"
SAMPLE_SELECTION_TASK = "sample_selection"


class _InfrastructureFields(BaseModel):
    """Fields the platform fills from the selected published dataset version."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    dataset_path: Path = Field(description="Path to the immutable dataset archive. AI Studio fills this from the published dataset version.")
    output_path: Path = Field(description="Directory for this job's outputs. The compute agent assigns a separate directory for each job.")
    mlflow_url: AnyHttpUrl | None = Field(default=None, description="MLflow tracking server URL. AI Studio supplies this infrastructure setting.")
    project_id: str = Field(min_length=1, description="Identifier of the AI Studio project that owns this job.")
    dataset_version_id: str = Field(min_length=1, description="Identifier of the frozen dataset version this job reads.")
    devices: tuple[str, ...] = Field(default=("cpu",), description="Requested compute devices: cpu or gpu. Availability depends on the compute agent and implementation.")
    random_seed: int = Field(default=42, description="Seed for any sampling or tie-breaking, so repeated jobs give the same result.")


class EmbeddingConfig(_InfrastructureFields):
    """Configuration for computing one embedding vector per dataset image.

    Implementations subclass this to add backbone or preprocessing options.
    """

    batch_size: int = Field(default=64, ge=1, description="Images embedded together in one forward pass. Larger batches need more memory.")
    image_size: int = Field(default=224, ge=1, description="Target image size in pixels. The implementation decides how images are resized or cropped.")
    normalize: bool = Field(default=True, description="L2-normalise each vector so cosine similarity equals the dot product.")


class SelectionConfig(_InfrastructureFields):
    """Configuration for choosing which unlabelled images to label next.

    The labelling budget is not configured here: the platform passes it per request in
    ``SelectionContext.budget``. Implementations subclass this for strategy options.
    """


@dataclass(frozen=True)
class EmbeddingSet:
    """A matrix of embeddings stored on disk, row ``i`` belonging to ``image_ids[i]``.

    ``path`` holds a float32 array of shape ``(len(image_ids), dim)``. The default media
    type is NumPy's ``.npy`` format; other formats must say so in ``media_type``.
    """

    path: Path
    image_ids: tuple[str, ...]
    dim: int
    model_key: str
    metric: Literal["cosine", "euclidean"] = "cosine"
    media_type: str = "application/x-npy"

    def __post_init__(self) -> None:
        if self.dim < 1:
            raise ValueError("dim must be at least 1")
        if len(set(self.image_ids)) != len(self.image_ids):
            raise ValueError("image_ids must be unique")


@dataclass(frozen=True)
class EmbeddingContext:
    job_id: str
    dataset: DatasetVersion
    output_dir: Path
    devices: tuple[str, ...] = ("cpu",)
    report_progress: Callable[..., None] | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class EmbeddingResult:
    embeddings: EmbeddingSet
    metrics: Mapping[str, float] = field(default_factory=dict)
    summary: str = ""


@dataclass(frozen=True)
class SelectionContext:
    """Everything a selector may use to rank the unlabelled pool.

    ``predictions`` maps image id to the current model's JSON predictions for that
    image, when a trained model exists. ``embeddings`` is present when the dataset
    version has an embedding job. Selectors must work with either one missing.
    """

    job_id: str
    dataset: DatasetVersion
    candidate_ids: tuple[str, ...]
    labelled_ids: tuple[str, ...]
    budget: int
    output_dir: Path
    predictions: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
    embeddings: EmbeddingSet | None = None
    model_key: str | None = None
    model_version: str | None = None
    report_progress: Callable[..., None] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.budget < 1:
            raise ValueError("budget must be at least 1")
        if set(self.candidate_ids) & set(self.labelled_ids):
            raise ValueError("candidate_ids and labelled_ids must not overlap")


@dataclass(frozen=True)
class SampleSuggestion:
    """One image proposed for labelling. A suggestion is never an accepted annotation."""

    image_id: str
    rank: int
    score: float
    reason: str = ""
    confidence: float | None = None
    model_key: str | None = None
    model_version: str | None = None


@dataclass(frozen=True)
class SelectionResult:
    suggestions: tuple[SampleSuggestion, ...]
    strategy: str
    metrics: Mapping[str, float] = field(default_factory=dict)
    summary: str = ""


def validate_selection(context: SelectionContext, result: SelectionResult) -> None:
    """Raise ``ValueError`` unless ``result`` is a legal answer to ``context``.

    Legal means: no more suggestions than the budget, only candidate images, no
    duplicates, and ranks 1..n in order.
    """
    ids = [s.image_id for s in result.suggestions]
    if len(ids) > context.budget:
        raise ValueError(f"{len(ids)} suggestions exceed the budget of {context.budget}")
    if len(set(ids)) != len(ids):
        raise ValueError("suggestions contain duplicate image ids")
    unknown = set(ids) - set(context.candidate_ids)
    if unknown:
        raise ValueError(f"suggestions include non-candidate images: {sorted(unknown)[:5]}")
    if [s.rank for s in result.suggestions] != list(range(1, len(ids) + 1)):
        raise ValueError("suggestion ranks must be 1..n in order")


EmbeddingConfigT = TypeVar("EmbeddingConfigT", bound=EmbeddingConfig)
SelectionConfigT = TypeVar("SelectionConfigT", bound=SelectionConfig)


def _validated(instance: object, config: Any, base: type[BaseModel]) -> Any:
    config_type = getattr(type(instance), "config_type", None)
    if not isinstance(config_type, type) or not issubclass(config_type, base):
        raise TypeError(f"{type(instance).__name__} must declare config_type as a {base.__name__} subclass")
    return config if isinstance(config, config_type) else config_type.model_validate(config)


class EmbeddingWorkbench(ABC, Generic[EmbeddingConfigT]):
    """Turns every image in a dataset version into a vector (task ``"embedding"``)."""

    config_type: ClassVar[type[EmbeddingConfig]]

    def __init__(self, config: EmbeddingConfigT | Mapping[str, Any]):
        self.config: EmbeddingConfigT = _validated(self, config, EmbeddingConfig)

    @classmethod
    @abstractmethod
    def descriptor(cls) -> ModelDescriptor:
        """Describe the embedder. ``task`` should be ``EMBEDDING_TASK``."""

    @abstractmethod
    def embed(self, context: EmbeddingContext) -> EmbeddingResult:
        """Embed every image in ``context.dataset`` and write the matrix under ``context.output_dir``."""

    @abstractmethod
    def embed_images(self, images: Sequence[Path]) -> Sequence[Sequence[float]]:
        """Embed ad-hoc images (for example a search query), in the same space as ``embed``."""


class SampleSelector(ABC, Generic[SelectionConfigT]):
    """Ranks unlabelled images to label next under a budget (task ``"sample_selection"``)."""

    config_type: ClassVar[type[SelectionConfig]]

    def __init__(self, config: SelectionConfigT | Mapping[str, Any]):
        self.config: SelectionConfigT = _validated(self, config, SelectionConfig)

    @classmethod
    @abstractmethod
    def descriptor(cls) -> ModelDescriptor:
        """Describe the strategy. ``task`` should be ``SAMPLE_SELECTION_TASK``."""

    @abstractmethod
    def select(self, context: SelectionContext) -> SelectionResult:
        """Return at most ``context.budget`` ranked suggestions from ``context.candidate_ids``."""
