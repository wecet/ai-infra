from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_interfaces import (
    EMBEDDING_TASK,
    SAMPLE_SELECTION_TASK,
    DatasetVersion,
    EmbeddingConfig,
    EmbeddingContext,
    EmbeddingResult,
    EmbeddingSet,
    EmbeddingWorkbench,
    ModelDescriptor,
    SampleSelector,
    SampleSuggestion,
    SelectionConfig,
    SelectionContext,
    SelectionResult,
    validate_selection,
)

DATASET = DatasetVersion("project", "v1", "Frames", "object_detection", Path("/data/v1.zip"), [])


def infra(**extra):
    return {"dataset_path": "/data/v1.zip", "output_path": "/out",
            "project_id": "project", "dataset_version_id": "v1", **extra}


class DinoConfig(EmbeddingConfig):
    backbone: str = "dinov2-small"


class DinoEmbedder(EmbeddingWorkbench[DinoConfig]):
    config_type = DinoConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor("dino", "DINOv2", EMBEDDING_TASK, "Self-supervised embeddings")

    def embed(self, context):
        ids = ("a", "b")
        return EmbeddingResult(EmbeddingSet(context.output_dir / "emb.npy", ids, 384, "dino"))

    def embed_images(self, images):
        return [[0.0] * 384 for _ in images]


class FirstN(SampleSelector[SelectionConfig]):
    config_type = SelectionConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor("first-n", "First N", SAMPLE_SELECTION_TASK, "Baseline")

    def select(self, context):
        picks = context.candidate_ids[: context.budget]
        return SelectionResult(
            tuple(SampleSuggestion(i, rank, 1.0) for rank, i in enumerate(picks, start=1)), "first-n")


def selection_context(**overrides):
    values = dict(job_id="job", dataset=DATASET, candidate_ids=("a", "b", "c"),
                  labelled_ids=("z",), budget=2, output_dir=Path("/out"))
    return SelectionContext(**{**values, **overrides})


def test_embedding_workbench_validates_config_and_runs():
    embedder = DinoEmbedder(infra(batch_size=8, backbone="dinov2-base"))
    assert embedder.config.batch_size == 8 and embedder.config.normalize
    result = embedder.embed(EmbeddingContext("job", DATASET, Path("/out")))
    assert result.embeddings.dim == 384 and result.embeddings.metric == "cosine"


def test_embedding_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        DinoEmbedder(infra(epochs=3))


def test_embedding_set_rejects_duplicates_and_empty_dim():
    with pytest.raises(ValueError):
        EmbeddingSet(Path("e.npy"), ("a", "a"), 8, "m")
    with pytest.raises(ValueError):
        EmbeddingSet(Path("e.npy"), ("a",), 0, "m")


def test_selector_returns_a_valid_selection():
    context = selection_context()
    result = FirstN(infra()).select(context)
    validate_selection(context, result)
    assert [s.image_id for s in result.suggestions] == ["a", "b"]


def test_selection_context_rejects_bad_budget_and_overlap():
    with pytest.raises(ValueError):
        selection_context(budget=0)
    with pytest.raises(ValueError):
        selection_context(labelled_ids=("a",))


@pytest.mark.parametrize("suggestions", [
    (SampleSuggestion("a", 1, 1), SampleSuggestion("b", 2, 1), SampleSuggestion("c", 3, 1)),
    (SampleSuggestion("a", 1, 1), SampleSuggestion("a", 2, 1)),
    (SampleSuggestion("z", 1, 1),),
    (SampleSuggestion("a", 2, 1),),
])
def test_validate_selection_rejects_illegal_results(suggestions):
    with pytest.raises(ValueError):
        validate_selection(selection_context(), SelectionResult(suggestions, "bad"))


def test_wrong_config_type_is_rejected():
    class Broken(SampleSelector[SelectionConfig]):
        config_type = EmbeddingConfig  # not a SelectionConfig

        @classmethod
        def descriptor(cls):
            return ModelDescriptor("x", "x", SAMPLE_SELECTION_TASK, "x")

        def select(self, context):
            raise NotImplementedError

    with pytest.raises(TypeError):
        Broken(infra())


def test_abstract_contracts_cannot_be_instantiated():
    with pytest.raises(TypeError):
        EmbeddingWorkbench(infra())
    with pytest.raises(TypeError):
        SampleSelector(infra())
