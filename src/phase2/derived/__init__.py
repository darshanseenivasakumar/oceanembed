"""Derived products built on top of the FROZEN TS-Cast-NIO model.

Nothing in this package retrains or modifies the checkpoint, the bundle, dataset.py, inference.py,
or the split. Each module consumes the model's reconstructed temperature (a profile or a field) and
turns it into an operational product.
"""
