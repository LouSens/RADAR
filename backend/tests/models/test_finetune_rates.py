"""Layer-wise learning rates, worked out from parameter names alone."""

import pytest

from radar.models import finetune


class Fake:
    """Stands in for a model: only the parameter names matter here."""

    def __init__(self, names: list[str]) -> None:
        self.names = names

    def named_parameters(self) -> list[tuple[str, object]]:
        return [(name, object()) for name in self.names]


@pytest.mark.parametrize("family", ["bert", "roberta", "deberta"])
def test_lower_layers_get_smaller_rates_in_every_family(family: str) -> None:
    model = Fake(
        [
            f"{family}.embeddings.word_embeddings.weight",
            f"{family}.encoder.layer.0.output.dense.weight",
            f"{family}.encoder.layer.1.output.dense.weight",
            f"{family}.encoder.layer.1.output.dense.bias",
            "classifier.weight",
        ]
    )
    groups = finetune._llrd_param_groups(
        model, learning_rate=1.0, weight_decay=0.01, layer_decay=0.5
    )
    rates = [group["lr"] for group in groups]
    # embeddings, layer 0, layer 1 (twice), head
    assert rates == pytest.approx([0.125, 0.25, 0.5, 0.5, 1.0])
    assert [group["weight_decay"] for group in groups] == [0.01, 0.01, 0.01, 0.0, 0.01]


def test_a_model_without_named_layers_is_refused_not_left_flat() -> None:
    with pytest.raises(AttributeError, match="No encoder layers"):
        finetune._llrd_param_groups(Fake(["head.weight"]), 1.0, 0.01, 0.9)
