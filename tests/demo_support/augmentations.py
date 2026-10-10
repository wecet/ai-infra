"""Torchvision transforms used by both on-the-fly training augmentors."""
import math

from torchvision.transforms import v2


def transforms_for(options, image):
    transforms = []
    probability = options.get("flip_probability", 0.5)
    if options.get("flip") in {"horizontal", "both"}:
        transforms.append(v2.RandomHorizontalFlip(probability))
    if options.get("flip") in {"vertical", "both"}:
        transforms.append(v2.RandomVerticalFlip(probability))
    if options.get("rotation", 0):
        transforms.append(v2.RandomRotation(options["rotation"]))
    if options.get("blur", 0):
        sigma = options["blur"]
        # Reflect padding cannot exceed a tiny image's dimensions.
        radius = min(math.ceil(3 * sigma), min(image.shape[-2:]) - 1)
        transforms.append(v2.GaussianBlur(2 * radius + 1, sigma=(sigma, sigma)))
    if any(options.get(name, 0) for name in ("brightness", "contrast", "saturation")):
        transforms.append(v2.ColorJitter(**{name: options.get(name, 0) for name in ("brightness", "contrast", "saturation")}))
    return v2.Compose(transforms) if transforms else v2.Identity()
