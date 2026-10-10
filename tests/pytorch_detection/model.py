from ai_interfaces import ModelDescriptor, ObjectDetectionModel
from torch import nn
from torchvision.models.detection import FasterRCNN
from torchvision.models.detection.anchor_utils import AnchorGenerator
from torchvision.ops import MultiScaleRoIAlign

from demo_support.utils import load_checkpoint
from pytorch_detection.config import DetectionConfig
from pytorch_detection.inference import predict
from pytorch_detection.trainer import train


class DemoDetector(ObjectDetectionModel[DetectionConfig]):
    config_type = DetectionConfig

    @classmethod
    def descriptor(cls):
        return ModelDescriptor(key="demo-pytorch-detector", name="PyTorch demo detector", task="object_detection", description="Faster R-CNN with a tiny CNN backbone; trained from scratch.")

    def build_network(self):
        config = self.config
        backbone = nn.Sequential(nn.Conv2d(3, config.channels, 3, stride=2, padding=1), nn.ReLU(),
                                 nn.Conv2d(config.channels, config.channels, 3, stride=2, padding=1), nn.ReLU())
        backbone.out_channels = config.channels
        return FasterRCNN(backbone, num_classes=len(config.class_names) + 1, min_size=config.image_size,
                          max_size=config.image_size, rpn_anchor_generator=AnchorGenerator(((8, 16, 32),), ((0.5, 1.0, 2.0),)),
                          box_roi_pool=MultiScaleRoIAlign(featmap_names=["0"], output_size=3, sampling_ratio=2),
                          rpn_pre_nms_top_n_train=100, rpn_post_nms_top_n_train=50,
                          rpn_pre_nms_top_n_test=100, rpn_post_nms_top_n_test=50,
                          box_score_thresh=config.score_threshold, box_nms_thresh=config.nms_threshold,
                          box_detections_per_img=config.max_detections)

    def gradcam_layer(self):
        return self.network.backbone[2]

    def gradcam_score(self, image):
        logits, transformed = [], []
        predictor_hook = self.network.roi_heads.box_predictor.register_forward_hook(lambda module, inputs, output: logits.append(output[0]))
        transform_hook = self.network.transform.register_forward_hook(lambda module, inputs, output: transformed.append(output[0]))
        try:
            self.network([image])
            # Explain the strongest foreground proposal before score filtering/NMS.
            foreground = logits[0][:, 1:]
            flat_index = foreground.argmax().item()
            class_index = flat_index % len(self.config.class_names)
            geometry = (transformed[0].image_sizes[0], transformed[0].tensors.shape[-2:])
            return foreground.flatten()[flat_index], self.config.class_names[class_index], geometry
        finally:
            predictor_hook.remove()
            transform_hook.remove()

    def train(self, context):
        return train(self, context)

    def load(self, artifact):
        load_checkpoint(self, artifact)

    def predict(self, image):
        return predict(self, image)
