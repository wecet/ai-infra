from demo_support.config import DemoConfig
from pydantic import Field


class DetectionConfig(DemoConfig):
    epochs: int = Field(default=2, ge=1)
    batch_size: int = Field(default=2, ge=1)
    image_size: int = Field(default=64, ge=32, le=1024)
    channels: int = Field(default=16, ge=4, le=128)
    score_threshold: float = Field(default=0.5, ge=0, le=1)
    nms_threshold: float = Field(default=0.5, gt=0, le=1)
    max_detections: int = Field(default=20, ge=1, le=100)
