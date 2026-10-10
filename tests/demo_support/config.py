"""Validated callback and augmentation options shared by both PyTorch demos."""
from typing import Annotated, Literal
from typing_extensions import TypedDict

from ai_interfaces import BaseModelConfig
from pydantic import ConfigDict, Field


class AugmentationOptions(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    blur: Annotated[float, Field(ge=0, le=10, description="Gaussian blur sigma; 0 disables blur.")]
    flip: Annotated[Literal["horizontal", "vertical", "both"], Field(description="Random flip direction.")]
    flip_probability: Annotated[float, Field(ge=0, le=1, description="Flip probability; defaults to 0.5.")]
    rotation: Annotated[float, Field(ge=0, le=180, description="Random rotation within +/- this many degrees.")]
    brightness: Annotated[float, Field(ge=0, le=1, description="Brightness jitter strength; 0 disables jitter.")]
    contrast: Annotated[float, Field(ge=0, le=1, description="Contrast jitter strength; 0 disables jitter.")]
    saturation: Annotated[float, Field(ge=0, le=1, description="Saturation jitter strength; 0 disables jitter.")]


class DemoConfig(BaseModelConfig):
    augmentations: AugmentationOptions = Field(default={}, title="Augmentations", description="Training-only augmentation options as a JSON object; an empty object disables augmentations.")
    callbacks: list[Literal["tensorboard", "gradcam"]] = Field(default=["tensorboard", "gradcam"], description="Enabled callbacks; select none to disable both. Grad-CAM images require TensorBoard.")
    gradcam_every_n_epochs: int = Field(default=1, ge=1, description="Generate Grad-CAM explanations every this many completed epochs. Set to 1 for every epoch. Requires both tensorboard and gradcam callbacks.")
    gradcam_samples: int = Field(default=1, ge=1, le=8, description="Maximum number of images to explain at each Grad-CAM logging interval. Uses unaugmented validation images, or training images when no validation set exists. More samples add computation.")
