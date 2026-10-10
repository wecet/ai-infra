"""Analytic check for Grad-CAM weighting and hook cleanup."""
import pytest
import torch
from torch import nn

from demo_support.gradcam import GradCAM


class ToyClassifier:
    def __init__(self):
        self.network = nn.Conv2d(3, 1, 1, bias=False)
        nn.init.ones_(self.network.weight)

    def gradcam_layer(self):
        return self.network

    def gradcam_score(self, image):
        return self.network(image.unsqueeze(0)).sum(), "target", None


def test_gradcam_matches_analytic_result_and_cleans_hooks():
    model = ToyClassifier()
    image = torch.arange(12, dtype=torch.float32).reshape(3, 2, 2) / 12
    callback = GradCAM(model)
    cam, label = callback.render(image)
    expected = image.sum(dim=0, keepdim=True)
    torch.testing.assert_close(cam, expected / expected.max())
    assert label == "target" and model.network.weight.grad is None
    assert not model.network._forward_hooks
    # An invalid input must also remove the hook after a failed forward pass.
    with pytest.raises(RuntimeError):
        callback.render(torch.zeros(2, 2, 2))
    assert not model.network._forward_hooks
