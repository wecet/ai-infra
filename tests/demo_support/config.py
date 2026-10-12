"""Validated callback and augmentation options shared by both PyTorch demos."""
from enum import Enum
from typing import Annotated
from typing_extensions import TypedDict

from ai_interfaces import BaseModelConfig
from pydantic import ConfigDict, Field, TypeAdapter, field_validator


class Callback(str, Enum):
    TENSORBOARD = "tensorboard"
    GRADCAM = "gradcam"


class Augmentation(str, Enum):
    BLUR = "blur"
    FLIP = "flip"
    FLIP_PROBABILITY = "flip_probability"
    ROTATION = "rotation"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATION = "saturation"


class FlipDirection(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    BOTH = "both"


class AugmentationOptions(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    blur: Annotated[float, Field(ge=0, le=10, description="Gaussian blur sigma; 0 disables blur.")]
    flip: Annotated[FlipDirection, Field(description="Random flip direction.")]
    flip_probability: Annotated[float, Field(ge=0, le=1, description="Flip probability; defaults to 0.5.")]
    rotation: Annotated[float, Field(ge=0, le=180, description="Random rotation within +/- this many degrees.")]
    brightness: Annotated[float, Field(ge=0, le=1, description="Brightness jitter strength; 0 disables jitter.")]
    contrast: Annotated[float, Field(ge=0, le=1, description="Contrast jitter strength; 0 disables jitter.")]
    saturation: Annotated[float, Field(ge=0, le=1, description="Saturation jitter strength; 0 disables jitter.")]


_augmentation_values = TypeAdapter(AugmentationOptions)
_augmentation_properties = _augmentation_values.json_schema()["properties"]
# Keep value descriptions/ranges alongside the enum of supported dictionary keys.
_augmentation_properties["flip"] = {**_augmentation_properties["flip"], "enum": [item.value for item in FlipDirection], "type": "string"}
_augmentation_properties["flip"].pop("$ref", None)


class DemoConfig(BaseModelConfig):
    augmentations: dict[Augmentation, float | FlipDirection] = Field(default={}, title="Augmentations", description="Training-only augmentation options as a JSON object; an empty object disables augmentations.", json_schema_extra={"properties": _augmentation_properties})
    callbacks: list[Callback] = Field(default=[Callback.TENSORBOARD, Callback.GRADCAM], description="Enabled callbacks; select none to disable both. Grad-CAM images require TensorBoard.")

    @field_validator("augmentations", mode="before")
    @classmethod
    def validate_augmentation_values(cls, value):
        return _augmentation_values.validate_python(value)

    gradcam_every_n_epochs: int = Field(default=1, ge=1, description="Generate Grad-CAM explanations every this many completed epochs. Set to 1 for every epoch. Requires both tensorboard and gradcam callbacks.")
    gradcam_samples: int = Field(default=1, ge=1, le=8, description="Maximum number of images to explain at each Grad-CAM logging interval. Uses unaugmented validation images, or training images when no validation set exists. More samples add computation.")
