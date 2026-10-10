"""Transform training images and boxes together, removing cropped-away boxes."""
import torch
from torchvision import tv_tensors
from torchvision.transforms import v2

from demo_support.augmentations import transforms_for


class Augmentor:
    def __init__(self, config):
        self.options = config.augmentations

    def __call__(self, image, target):
        if not self.options:
            return image, target
        boxes = tv_tensors.BoundingBoxes(target["boxes"], format="XYXY", canvas_size=image.shape[-2:])
        image, target = transforms_for(self.options, image)(tv_tensors.Image(image), {**target, "boxes": boxes})
        image, target = v2.ClampBoundingBoxes()(image, target)
        # Keep valid subpixel boxes; Torchvision's sanitizer requires >= 1 pixel.
        keep = (target["boxes"][:, 2:] > target["boxes"][:, :2]).all(dim=1)
        target = {**target, "boxes": target["boxes"][keep], "labels": target["labels"][keep]}
        return image.as_subclass(torch.Tensor), {**target, "boxes": target["boxes"].as_subclass(torch.Tensor)}
