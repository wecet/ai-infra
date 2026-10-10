import torch
from torch.nn.functional import binary_cross_entropy_with_logits

from demo_support.training import train as run_training
from pytorch_classification.augmentor import Augmentor


def loss_for(network, images, targets, device):
    return binary_cross_entropy_with_logits(network(torch.stack(images).to(device)), torch.stack(targets).to(device))


def train(model, context):
    return run_training(model, context, loss_for, Augmentor(model.config))
