"""Run the tone pipeline of decision 101 from start to finish, saying what each step found.

    uv run python backend/scripts/tone_round4.py          # steps 1 to 6 (hours on one GPU)
    uv run python backend/scripts/tone_round4.py test     # step 7: the test set, once

Every step is stored under `data/research/tone4/`, so a run that stops can be started
again and picks up where it was.
"""

import sys
import warnings

from transformers.utils import logging as model_logging

from radar.pipelines import tone

warnings.filterwarnings("ignore")
model_logging.disable_progress_bar()
model_logging.set_verbosity_error()


def say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def table(options: dict[str, dict[str, float]]) -> None:
    for name, found in sorted(options.items(), key=lambda item: item[1]["loss"]):
        say(
            f"   {name:<46} validation error {found['loss']:.4f}   "
            f"right {found['accuracy']:.1%}   training error {found['training_loss']:.3f}"
        )


def main(test: bool) -> None:
    data = tone.load()
    say(f"{len(data.labelled)} training and validation headlines, {len(data.test)} test")
    say(tone.agreement(data).round(3).to_string())
    for train, validation in tone.blocks(data):
        say(
            f"   block: train {len(train)} to {train['created_at'].max():%Y-%m-%d}, "
            f"validate {len(validation)} to {validation['created_at'].max():%Y-%m-%d}"
        )
    step = tone.choose_text(data)
    say(f"step 1, text: {step['winner']}")
    table(step["options"])
    step = tone.choose_model(data)
    say(f"step 2, base model: {step['winner']}")
    table(step["options"])
    step = tone.choose_settings(data)
    for group in step["groups"]:
        say(f"step 3: {group['winner']}")
        table(group["options"])
    found = tone.final(data)
    say(f"pool: {found['pool']}")
    for name, stage in found["stages"].items():
        say(f"   {name}: {stage['together']}  kept passes {stage['kept']}")
    say(f"kept: {found['kept']}; temperature {found['temperature']:.2f}")
    say(f"validation after the temperature: {found['validation_after']}")
    if test:
        result = tone.test_once(data)
        say(f"test, {result['headlines']} headlines")
        for name, score in result["scores"].items():
            say(f"   {name}: right {score['accuracy']:.1%}, error {score['loss']:.4f}")
        say(f"   {result['comparison']}")
        say(f"   by market: {result['by_market']}")
        gaps = f"{result['accuracy_gap']:.3f} right, {result['loss_gap']:.3f} error"
        say(f"   gap to validation: {gaps}")
        say(f"   bars: {result['bars']}")


if __name__ == "__main__":
    main(sys.argv[1:] == ["test"])
