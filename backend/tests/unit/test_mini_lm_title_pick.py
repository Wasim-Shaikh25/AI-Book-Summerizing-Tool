"""Tests for MiniLM title pick helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from src.modules.structure.final_structuring.models.mini_lm_title_pick import mini_lm_pick_title


@patch("src.modules.structure.final_structuring.models.mini_lm_title_pick.get_mini_lm_encoder")
def test_mini_lm_pick_returns_best_candidate(mock_get_encoder) -> None:
    encoder = MagicMock()
    mock_get_encoder.return_value = encoder
    encoder.encode.side_effect = [
        np.array([[1.0, 0.0]]),
        np.array([[1.0, 0.0], [0.0, 1.0]]),
    ]

    picked = mini_lm_pick_title(
        "(Art. 14)",
        preview="Equality before the law applies to all citizens.",
        subheadings=["Equality before the law (Art. 14)"],
        threshold=0.5,
    )
    assert picked == "Equality before the law (Art. 14)"


@patch("src.modules.structure.final_structuring.models.mini_lm_title_pick.get_mini_lm_encoder")
def test_mini_lm_pick_below_threshold_returns_none(mock_get_encoder) -> None:
    encoder = MagicMock()
    mock_get_encoder.return_value = encoder
    encoder.encode.side_effect = [
        np.array([[1.0, 0.0]]),
        np.array([[0.0, 1.0]]),
    ]

    picked = mini_lm_pick_title("(ii)", preview="unrelated topic", threshold=0.82)
    assert picked is None
