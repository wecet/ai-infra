# PyTorch demo workbenches

Each model has `config.py` (Pydantic), `model.py` (the established task ABC),
`trainer.py`, `inference.py`, `augmentor.py`, and the two agent discovery files. `demo_support`
shares ZIP reading, device checks, checkpoint loading and the training loop.

From the repository root, using Python 3.11 or 3.12:

```sh
python3.11 -m venv tests/.venv
tests/.venv/bin/python -m pip install -r tests/requirements.txt
tests/.venv/bin/python tests/smoke.py
```

This installs the repository's current `ai-infra-interfaces` package, PyTorch and
Torchvision into an isolated environment. No pretrained weights are downloaded.
The smoke check creates synthetic Studio datasets and exercises discovery,
training, validation, checkpoint reload and predictions for both tasks.

Rebuild the services with `docker compose up -d --build training-agent tensorboard labelling`.
The configured workspace mount must include this repository. In AI Studio,
publish a dataset version, open Training, and select the matching **PyTorch demo**
model. Pydantic exposes all model options in the existing hyperparameter form.

Classification uses a tiny CNN with sigmoid outputs and binary cross-entropy,
including multiple or empty labels. Detection uses Torchvision Faster R-CNN with
a tiny CNN backbone, multiple boxes per image, and empty-image targets. Detection
predictions use original-image pixel `bbox: [x, y, width, height]` coordinates;
both tasks return `class_name` and `score`. Checkpoints preserve the configuration,
class order and weights, and load with `weights_only=True`.

Training reads the context's immutable archive and writes `model.pt` only under
the context output directory. Both models report train loss and validation loss
when a holdout exists. The agent handles MLflow. These models train from scratch
and demonstrate integration; meaningful accuracy requires representative data and
more training. One device is used per run. Default agent wheels support CPU;
CUDA agents can build with `--build-arg PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128`.

## Live metrics and Grad-CAM

The Pydantic `callbacks` list defaults to `["tensorboard", "gradcam"]`. Select
callbacks in the Training form dropdown; select **None** to disable both.
Batch losses flush during training. Train/validation losses and learning rate log
at every epoch. `gradcam_every_n_epochs` controls the image callback interval and
`gradcam_samples` limits how many fixed validation images it explains (training
images are used if there is no holdout). Grad-CAM images are written only when
both callbacks are enabled. The
**View live metrics** button appears only when both are selected and the selected
agent advertises a dashboard URL.

The classifier explains its highest class logit. The detector explains the
highest foreground proposal logit before score filtering and NMS, including when
no final detection meets the confidence threshold. Heatmaps remove detector resize
padding and align with the original sample. TensorBoard's Images tab shows the
input, normalized heatmap and overlay; its Text tab shows the target class.

**View live metrics** opens the selected agent's TensorBoard dashboard in a new
tab (default http://localhost:6006). Choose a job's `<job_id>/tensorboard` run in
TensorBoard. Scalar curves and Grad-CAM images remain after completion or an agent
restart in the `ai-infra_training_runs` Docker volume. Only event files remain on
the agent after a successful run; Studio stores the downloaded model artifact.

Standalone model training writes events under `context.output_dir/tensorboard`.
Run `tests/.venv/bin/tensorboard --logdir /path/to/outputs` to view them locally.
TensorBoard is published only on the host loopback interface. For remote agents,
run TensorBoard on the same training-runs volume, access it through an SSH tunnel
or secured reverse proxy, and set `TENSORBOARD_PUBLIC_URL` to that browser-reachable
URL. An agent without that setting advertises no dashboard, and the button remains hidden until a remote
connection has been tested.

## On-the-fly training augmentations

Each model's `augmentor.py` applies the `augmentations` dictionary at sample load
time. Defaults are `{}` (no augmentation). For example:

```json
{
  "blur": 0.8,
  "flip": "vertical",
  "flip_probability": 0.5,
  "rotation": 15,
  "brightness": 0.2,
  "contrast": 0.2,
  "saturation": 0.2
}
```

Blur specifies Gaussian sigma (0–10); flip is `horizontal`, `vertical`, or `both`,
with probability 0–1 (default 0.5 for each direction). Rotation randomly samples
within ± the supplied degrees (0–180). Brightness, contrast and saturation strengths
are 0–1 and randomly vary around the original value. Unknown keys, unsupported
choices and out-of-range values fail Pydantic validation.

Detection boxes follow the same geometric transforms; boxes are clamped to the
image and cropped-away boxes and their labels are removed together. Validation,
inference, and Grad-CAM examples use unaugmented images. The frozen ZIP is never
modified. The Training form prepopulates schema defaults, uses a JSON text area
with supported-option hints for augmentations, and restores defaults for blank
inputs on submission. An explicitly empty callbacks list remains empty.

Additional checks:

```sh
tests/.venv/bin/python -m pip install pytest==9.1.1
PYTHONPATH=tests tests/.venv/bin/python -m pytest tests/test_augmentations.py tests/test_gradcam.py -q
node --test src/labelling/frontend/tests/training-config.test.js
```

### Field descriptions in AI Studio

Both demo configs provide descriptions for every field, including inherited training settings and model-specific inference options. Shared descriptions live in `BaseModelConfig` and `demo_support/config.py`; task-specific descriptions live in each model's `config.py`.

Use Pydantic's `Field(description="...")` to explain a configuration variable:

```python
gradcam_samples: int = Field(default=1, ge=1, le=8, description="Number of validation images to explain with Grad-CAM each time the callback runs.")
```

AI Studio shows this description in a closable popup beside the field label. Fields without a description show `No description defined`.

### Trainer errors

Raise a normal Python exception with a useful message when training cannot continue. The agent returns the exception type and message as an HTTP error, and AI Studio records the run as failed and shows its error in a closable popup. The temporary dataset is cleaned up, the agent remains available, and the form retains your configuration for retry. Existing failed runs remain visible in the jobs table without reopening popups on every refresh.

TensorBoard's **Time Series** view includes batch loss, epoch training and validation loss, learning rate, epoch duration, and Grad-CAM images. Classification also logs per-label binary accuracy (at threshold 0.5); detection logs classifier, box regression, objectness and RPN box regression loss components for training and validation. The same final epoch metrics are recorded in MLflow. Validation metrics require a nonempty validation split; disabled validation does not produce invented validation values.
