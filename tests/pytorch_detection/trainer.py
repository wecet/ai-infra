from demo_support.training import train as run_training
from pytorch_detection.augmentor import Augmentor


def loss_for(network, images, targets, device):
    images = [image.to(device) for image in images]
    targets = [{name: value.to(device) for name, value in target.items()} for target in targets]
    losses = network(images, targets)
    return sum(losses.values()), {key: value.detach().item() for key, value in losses.items()}


def train(model, context):
    return run_training(model, context, loss_for, Augmentor(model.config))
