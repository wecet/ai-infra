"""Apply augmentations to training images while preserving whole-image labels."""
from demo_support.augmentations import transforms_for


class Augmentor:
    def __init__(self, config):
        self.options = config.augmentations

    def __call__(self, image, target):
        return transforms_for(self.options, image)(image), target
