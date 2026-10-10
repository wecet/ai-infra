import torch
from PIL import Image

from demo_support.data import image_tensor


def predict(model, image):
    with Image.open(image) as source:
        tensor = image_tensor(source)
    model.network.eval()
    with torch.inference_mode():
        result = model.network([tensor])[0]
    return [{"class_name": model.config.class_names[label - 1], "score": score,
             "bbox": [box[0], box[1], box[2] - box[0], box[3] - box[1]]}
            for label, score, box in zip(result["labels"].tolist(), result["scores"].tolist(), result["boxes"].tolist())]
