"""Fix basicsr compatibility with newer torchvision"""
import sys

# Monkey patch for torchvision compatibility
try:
    import torchvision.transforms.functional_tensor
except (ImportError, ModuleNotFoundError):
    import torchvision.transforms.functional as F
    sys.modules['torchvision.transforms.functional_tensor'] = F
