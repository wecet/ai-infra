import torch
from torch.nn.functional import binary_cross_entropy_with_logits

from demo_support.training import train as run_training
from pytorch_classification.augmentor import Augmentor


def loss_for(network, images, targets, device):
    logits = network(torch.stack(images).to(device))
    labels = torch.stack(targets).to(device)
    loss = binary_cross_entropy_with_logits(logits, labels)
    accuracy = ((logits.detach().sigmoid() >= 0.5) == labels.bool()).float().mean()
    return loss, {"label_accuracy": accuracy.item()}


def train(model, context):
    return run_training(model, context, loss_for, Augmentor(model.config))
