"""Entry point supports discovery and in-process agent loading."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pytorch_classification.model import DemoClassifier

MODEL_CLASS = DemoClassifier
