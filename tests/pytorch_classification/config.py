from demo_support.config import Augmentation, Callback, DemoConfig, FlipDirection
from pydantic import Field


class ClassificationConfig(DemoConfig):
    epochs: int = Field(default=2, ge=1, description="Number of complete passes through the training images. More epochs take longer and can overfit a small dataset.")
    batch_size: int = Field(default=4, ge=1, description="Number of images processed together in each optimizer step. Reduce this if training runs out of memory.")
    image_size: int = Field(default=64, ge=16, le=1024, description="Width and height in pixels used to resize every image to a square for training and inference. Larger images preserve more detail but use more memory.")
    channels: int = Field(default=16, ge=4, le=128, description="Number of feature channels in the CNN backbone. Larger values increase model capacity, memory use and training time.")
    score_threshold: float = Field(default=0.5, ge=0, le=1, description="Minimum sigmoid score for returning a class during inference. Each class is scored independently, so an image may receive multiple labels or none. Lower values return more labels.")
