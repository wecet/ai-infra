from demo_support.config import Augmentation, Callback, DemoConfig, FlipDirection
from pydantic import Field


class DetectionConfig(DemoConfig):
    epochs: int = Field(default=2, ge=1, description="Number of complete passes through the training images. More epochs take longer and can overfit a small dataset.")
    batch_size: int = Field(default=2, ge=1, description="Number of images processed together in each optimizer step. Reduce this if training runs out of memory.")
    image_size: int = Field(default=64, ge=32, le=1024, description="Maximum image side length in pixels used by Faster R-CNN. Images are resized with their aspect ratio preserved; larger values retain more detail but use more memory.")
    channels: int = Field(default=16, ge=4, le=128, description="Number of feature channels in the CNN backbone. Larger values increase model capacity, memory use and training time.")
    score_threshold: float = Field(default=0.5, ge=0, le=1, description="Minimum confidence score for returning a detected object during inference. Lower values return more boxes, including less certain detections.")
    nms_threshold: float = Field(default=0.5, gt=0, le=1, description="Intersection-over-union threshold for suppressing overlapping boxes of the same class during inference. Lower values remove overlapping detections more aggressively.")
    max_detections: int = Field(default=20, ge=1, le=100, description="Maximum number of detected objects returned per image after confidence filtering and overlap suppression.")
