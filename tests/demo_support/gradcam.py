"""Epoch callback using class-logit Grad-CAM, including pre-NMS detector logits."""
import torch
from torch.nn.functional import interpolate


class GradCAM:
    def __init__(self, model):
        self.model = model

    def render(self, image):
        activations = []
        handle = self.model.gradcam_layer().register_forward_hook(lambda module, inputs, output: activations.append(output))
        try:
            with torch.enable_grad():
                score, label, geometry = self.model.gradcam_score(image)
                activation = activations[0]
                gradient = torch.autograd.grad(score, activation)[0]
                cam = (gradient.mean(dim=(-2, -1), keepdim=True) * activation).sum(dim=1, keepdim=True).relu()
                if geometry is not None:
                    resized, padded = geometry
                    cam = interpolate(cam, size=padded, mode="bilinear", align_corners=False)
                    cam = cam[:, :, :resized[0], :resized[1]]
                cam = interpolate(cam, size=image.shape[-2:], mode="bilinear", align_corners=False)[0].detach()
                cam = cam / cam.max().clamp_min(1e-8)
                return cam.cpu(), label
        finally:
            handle.remove()

    def on_epoch_end(self, writer, samples, epoch, device):
        network = self.model.network
        was_training = network.training
        network.eval()
        try:
            for index in range(min(len(samples), self.model.config.gradcam_samples)):
                image, _ = samples[index]
                cam, label = self.render(image.to(device))
                original = image.detach().cpu()
                color = torch.cat((cam, torch.zeros_like(cam), 1 - cam), dim=0)
                overlay = original * (1 - cam * 0.5) + color * cam * 0.5
                tag = f"GradCAM/sample_{index}"
                writer.add_image(f"{tag}/input", original, epoch)
                writer.add_image(f"{tag}/heatmap", cam, epoch)
                writer.add_image(f"{tag}/overlay", overlay, epoch)
                writer.add_text(f"{tag}/target_class", label, epoch)
        finally:
            network.train(was_training)
