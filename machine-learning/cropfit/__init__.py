"""CropFit demo vector map and optional experimental training modules."""

__all__ = ["CropFitPredictor"]


def __getattr__(name: str):
    if name == "CropFitPredictor":
        from .inference import CropFitPredictor
        return CropFitPredictor
    raise AttributeError(name)
