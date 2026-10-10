"""Device selection and portable checkpoint loading."""
import torch


def device_for(devices):
    if len(devices) != 1:
        raise ValueError("Demo models support exactly one device")
    name = devices[0]
    if name == "gpu":
        name = "cuda"
    if name not in {"cpu", "cuda", "mps"}:
        raise ValueError("Supported devices: cpu, gpu/cuda, mps")
    if name == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is unavailable")
    if name == "mps" and not torch.backends.mps.is_available():
        raise ValueError("MPS is unavailable")
    return torch.device(name)


def load_checkpoint(model, artifact):
    checkpoint = torch.load(artifact, map_location="cpu", weights_only=True)
    model.config = model.config_type.model_validate(checkpoint["config"])
    model.network = model.build_network()
    model.network.load_state_dict(checkpoint["state_dict"])
    model.network.eval()
