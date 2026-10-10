from ai_interfaces import ImageClassificationModel, ModelDescriptor
from torch import nn

from demo_support.utils import load_checkpoint
from pytorch_classification.config import ClassificationConfig
from pytorch_classification.inference import predict
from pytorch_classification.trainer import train


class DemoClassifier(ImageClassificationModel[ClassificationConfig]):
    config_type = ClassificationConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor(key="demo-pytorch-classifier", name="PyTorch demo classifier", task="image_classification", description="Small CNN with multi-label classification; trained from scratch.")

    def build_network(self):
        channels = self.config.channels
        return nn.Sequential(nn.Conv2d(3, channels, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                             nn.Conv2d(channels, channels * 2, 3, padding=1), nn.ReLU(),
                             nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(channels * 2, len(self.config.class_names)))

    def gradcam_layer(self):
        return self.network[3]

    def gradcam_score(self, image):
        logits = self.network(image.unsqueeze(0))[0]
        index = logits.argmax().item()
        return logits[index], self.config.class_names[index], None

    def train(self, context):
        return train(self, context)

    def load(self, artifact):
        load_checkpoint(self, artifact)

    def predict(self, image):
        return predict(self, image)
