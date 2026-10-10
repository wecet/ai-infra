import torch
from PIL import Image

from demo_support.data import image_tensor


def predict(model, image):
    with Image.open(image) as source:
        tensor = image_tensor(source, model.config.image_size)
    model.network.eval()
    with torch.inference_mode():
        scores = model.network(tensor.unsqueeze(0)).sigmoid()[0].tolist()
    return [{"class_name": name, "score": score} for name, score in zip(model.config.class_names, scores)
            if score >= model.config.score_threshold]
