"""Compatibility entry point for add-in loaders that use main.py."""

try:
    from .math_curve_2 import run, stop
except ImportError:
    from math_curve_2 import run, stop


__all__ = ("run", "stop")
