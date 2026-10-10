"""Shared demo training loop with live TensorBoard metrics and Grad-CAM images."""
import json
from contextlib import nullcontext

import torch
from ai_interfaces import ModelArtifact, TrainingResult
from torch.utils.data import DataLoader, Subset
from torch.utils.tensorboard import SummaryWriter

from demo_support.data import StudioDataset, collate
from demo_support.gradcam import GradCAM
from demo_support.utils import device_for


def train(model, context, loss_for, augmentor):
    config = model.config
    torch.manual_seed(config.random_seed)
    device = device_for(context.devices)
    model.network = model.build_network().to(device)
    dataset = StudioDataset(context.dataset.archive, config, model.descriptor().task)
    order = torch.randperm(len(dataset)).tolist()
    count = min(len(dataset) - 1, max(1, int(len(dataset) * config.validation_split))) if config.validation_split else 0
    validation = Subset(dataset, order[:count])
    augmented = StudioDataset(context.dataset.archive, config, model.descriptor().task, augmentor)
    training = Subset(augmented, order[count:])
    cam_samples = validation if len(validation) else Subset(dataset, order[count:])
    loader = DataLoader(training, batch_size=config.batch_size, shuffle=True, collate_fn=collate)
    optimizer = torch.optim.Adam(model.network.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    logging = SummaryWriter(str(context.output_dir / "tensorboard"), flush_secs=1) if "tensorboard" in config.callbacks else nullcontext()
    gradcam = GradCAM(model) if "gradcam" in config.callbacks else None
    metrics, step = {}, 0
    with logging as writer:
        if writer:
            writer.add_text("Run/config", json.dumps(config.model_dump(mode="json"), indent=2))
            writer.add_text("Run/job_id", context.job_id)
            writer.flush()
        for epoch in range(1, config.epochs + 1):
            model.network.train()
            total = 0.0
            for images, targets in loader:
                optimizer.zero_grad()
                loss = loss_for(model.network, images, targets, device)
                if not torch.isfinite(loss):
                    raise ValueError("Training loss is not finite")
                loss.backward()
                optimizer.step()
                total += loss.item() * len(images)
                step += 1
                if writer:
                    writer.add_scalar("Loss/batch", loss.item(), step)
                    writer.flush()
            metrics["train_loss"] = total / len(training)
            if len(validation):
                # Detection returns losses in train mode; this backbone has no BatchNorm/dropout.
                model.network.train(model.descriptor().task == "object_detection")
                with torch.no_grad():
                    total = sum(loss_for(model.network, images, targets, device).item() * len(images)
                                for images, targets in DataLoader(validation, batch_size=config.batch_size, collate_fn=collate))
                metrics["validation_loss"] = total / len(validation)
            if writer:
                writer.add_scalar("Loss/train", metrics["train_loss"], epoch)
                if "validation_loss" in metrics:
                    writer.add_scalar("Loss/validation", metrics["validation_loss"], epoch)
                writer.add_scalar("LearningRate", optimizer.param_groups[0]["lr"], epoch)
                if gradcam and epoch % config.gradcam_every_n_epochs == 0:
                    gradcam.on_epoch_end(writer, cam_samples, epoch, device)
                writer.flush()
    model.network.cpu().eval()
    artifact = context.output_dir / "model.pt"
    torch.save({"config": config.model_dump(mode="json"), "state_dict": model.network.state_dict()}, artifact)
    return TrainingResult(metrics=metrics, artifact=ModelArtifact(artifact), summary=f"Trained on {len(training)} images; validated on {len(validation)}.")
