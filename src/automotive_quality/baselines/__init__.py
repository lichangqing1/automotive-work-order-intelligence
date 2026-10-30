"""Explicit comparison baselines; never the production AI or retrieval runtime."""

from .deterministic_ai import assist_resolution, build_rca, generate_rule

__all__ = ["assist_resolution", "build_rca", "generate_rule"]
