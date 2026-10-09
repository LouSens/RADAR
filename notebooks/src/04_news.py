# %% [markdown]
# # News tone: a three-class classifier for financial headlines
#
# This notebook reports how the tone model was built and how well it works. It follows
# the pipeline stage by stage. It trains nothing and scores nothing: every figure is
# read from a file the pipeline stored (`data/research/tone4/`), and a figure whose file
# is missing is shown as "not available" with the path. No real headline is printed;
# the examples are made up. The plan and its pass marks were written before the run
# (`docs/DECISIONS.md`, decision 101); where the code departs from that plan is listed in
# decision 102.

# %%
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display

warnings.filterwarnings("ignore")  # notices from the model library
from transformers.utils import logging as model_logging

model_logging.set_verbosity_error()

from radar.models import dataset
from radar.notebooks import ACCENT, INK, MUTED, caption, say, tidy, use_style
from radar.pipelines import finetune as finetune_job
from radar.pipelines import tone
from radar.pipelines import tone_report as report

use_style()
pd.set_option("display.float_format", lambda value: f"{value:,.3f}")
LABELS = tone.LABELS
data = tone.load()
step1, step2, step3 = (report.stored(n) for n in ("step1_text", "step2_model", "step3_settings"))
final, test = report.stored("final"), report.stored("test")
agree = report.agreement(data)
share = float(agree.loc["all", "agreement"])
low, high = report.reachable(share)
blocks = report.block_table(data)
last_n = int(blocks.loc[f"block {tone.BLOCKS}", "validated on"])

# %% [markdown]
# ## 0. Summary
#
# **Question.** Can the tone of a headline (positive, negative or neutral) be read by a
# model more accurately than by the one the app uses today, without overfitting?

# %%
say(
    f"1. **Labels.** Two labelling passes of the same {int(agree.loc['all', 'headlines'])} "
    f"headlines agree on {share:.1%}. That puts the best reachable accuracy between "
    f"{low:.1%} and {high:.1%} (section 3)."
)
say(
    f"2. **Validation.** {report.not_available('final')}"
    if final is None
    else f"2. **Validation.** The kept model ({final['kept']}; {final['choice']['model_name']}) "
    f"reaches accuracy {final['validation_after']['accuracy']:.1%} and loss "
    f"{final['validation_after']['loss']:.3f} on the last validation block "
    f"({final['validation']} headlines). Validation figures lean optimistic (section 6)."
)
say(
    f"3. **Test.** {report.not_available('test')}. The test has not been run."
    if test is None
    else f"3. **Test.** On {test['headlines']} unseen headlines the new model's accuracy is "
    f"{test['scores']['new']['accuracy']:.1%} (95% range {test['scores']['new']['from']:.1%} to "
    f"{test['scores']['new']['to']:.1%}) against {test['scores']['in use']['accuracy']:.1%} for "
    f"the model in the app. Better than the model in use: "
    f"**{'pass' if test['bars']['better than the model in use'] else 'fail'}**. Not overfitted: "
    f"**{'pass' if test['bars']['not overfitted'] else 'fail'}** (section 10)."
)

# %%
if test is None:
    say(f"Results table: {report.not_available('test')}")
else:
    display(tidy(report.test_scores(test)))
    caption(
        f"Test set: {test['headlines']} headlines, {test['from'][:10]} to {test['to'][:10]}. "
        "Accuracy is a share from 0 to 1."
    )

# %% [markdown]
# ## 1. Problem and metric
#
# *What is predicted, and how is a good prediction measured?*
#
# The input is one headline. The output is a probability for each label; the label with
# the highest probability is the answer. Terms used throughout, each with one meaning:
#
# | Term | Meaning |
# |---|---|
# | accuracy | Share of headlines whose answer matches the label |
# | loss | Log loss (cross-entropy): the average of minus the log of the probability given to the true label. It counts how sure the model was, so a confident wrong answer costs more than an unsure one |
# | macro F1 | F1 worked out per label and averaged, so a rare label counts as much as a common one |
# | pass | One run through all training headlines (an "epoch") |
# | seed | The number that fixes the random order of training; the same recipe with another seed gives a slightly different model |
# | block | A stretch of headlines, later in time than everything the model was trained on, used to validate |
# | validation | Headlines used to make choices. The test set is used for none |
#
# Accuracy is what a reader of the app experiences. Loss is used to make choices because
# it uses the whole probability, not only which label came first, so it moves less from
# one run to the next on a few hundred headlines.

# %%
say(
    f"There are {len(LABELS)} labels: {', '.join(LABELS)}. A model that gives each label "
    f"the same probability has a loss of {report.KNOWS_NOTHING:.3f} (the log of {len(LABELS)}), "
    "the mark an untrained model would score."
)
say(
    "**The two bars**, written in decision 101 before the run and read on the test set: "
    f"(1) *better than the model in use*: higher accuracy than `{finetune_job.MODEL_DIR.name}`, "
    f"with McNemar's test giving p below {tone.P_BELOW}; "
    f"(2) *not overfitted*: test accuracy no more than {tone.ACCURACY_GAP * 100:.0f} points under "
    f"validation accuracy, and test loss no more than {tone.LOSS_GAP:.2f} above validation loss."
)

# %% [markdown]
# ## 2. Data
#
# *What is there to learn from, and who labelled it?*

# %%
counts = report.counts(data)
writers = sorted(set(data.labelled["labelled_by"]) | set(data.test["labelled_by"]))
say(
    f"Headlines come from the app's stored news (table `news_articles`) and are joined to "
    f"their labels by article number. Labels live in three files in `backend/src/radar/`: "
    f"`{finetune_job.TRAINING_LABELS_FILE}`, `{finetune_job.REPLICATION_LABELS_FILE}` and "
    f"`{tone.ROUND4_LABELS_FILE}`. Every label was written by: **{', '.join(writers)}** "
    "(an AI model, not a person), from the headline alone."
)
display(counts["by market and label"])
caption(
    f"Training and validation headlines by market and label: {len(data.labelled):,} headlines, "
    f"{report.window(data.labelled)}."
)

# %%
display(counts["by year"].T)
caption(f"The same {len(data.labelled):,} headlines by year published.")

# %%
display(counts["test by month"].T)
caption(
    f"Test set by market and month: {len(data.test):,} headlines, {report.window(data.test)}. "
    "Its labels are not read in this notebook."
)

# %% [markdown]
# **The labelling rule**, quoted from decision 101:
#
# > Judged from the headline alone, as a financial reader would take it:
# >
# > - *positive*: it reports or expects something good for prices or holders (gains, a
# >   beat, inflows, approval, adoption, a bullish call, easing of a threat);
# > - *negative*: the opposite (falls, a miss, outflows, a ban, a hack, a lawsuit,
# >   conflict, a central banker leaning towards higher rates, a bearish call);
# > - *neutral*: no clear direction (a plain fact or scheduled figure without a stated
# >   surprise, procedure, a mixed wrap with one thing up and another down, a question,
# >   or something off the subject);
# > - when the headline names the asset it is filed under, what it says about that asset
# >   decides; otherwise its overall tone does.

# %%
gold_test = int((data.test["market"] == "Gold").sum())
say(
    f"**Found.** {len(data.labelled):,} headlines are available to train and choose on and "
    f"{len(data.test):,} to test on. Gold has {gold_test} test headlines, too few for a "
    "figure of its own."
)

# %% [markdown]
# ## 3. Data quality
#
# *Are the headlines clean, are there repeats, and how far can the labels be trusted?*
#
# **Near-copies.** Many headlines are templates that differ only in a number. Each is
# reduced to a key (lower case, numbers replaced by `#`, punctuation removed), and a key
# may appear once across all labelled sets (`dataset.headline_key`, `dataset.drop_repeats`).

# %%
keys = report.near_copies(data)
display(pd.Series(keys, name="count").to_frame())
caption("If headlines and distinct keys are equal, no near-copy is left within a part.")

# %% [markdown]
# **Cleaning** (`dataset.clean_headline`) removes what carries no tone and leaves the
# words as they are: white space is evened out, HTML entities are read, and a revision
# note, an exchange tag and a source after a closing quote are removed.

# %%
made_up = [
    "Gold &amp; Silver   Rise As Dollar Slips (UPDATED)",
    "Analyst Praises Example Corp (NYSE:EXMP) After Earnings",
    "'Example Bank Cuts Its Forecast' - Example Wire",
]
display(pd.DataFrame({"as stored": made_up, "as cleaned": map(dataset.clean_headline, made_up)}))
caption("Three made-up headlines, before and after cleaning.")

# %% [markdown]
# **Inter-pass agreement.** A sample of the old headlines was labelled a second time,
# mixed among new ones so the labeller could not tell them apart. Cohen's kappa is the
# agreement beyond what two labellers would reach by chance (1 is full agreement, 0 is
# chance).

# %%
display(tidy(agree))
caption(
    f"Two labelling passes on {int(agree.loc['all', 'headlines'])} headlines drawn from the "
    f"training and validation set ({report.window(data.labelled.dropna(subset=['second']))})."
)

# %%
display(report.agreement_grid(data))
caption("The same headlines: first pass in rows, second pass in columns.")

# %%
say(
    f"**What this bounds.** Inter-pass agreement is {share:.1%} (kappa "
    f"{agree.loc['all', 'kappa']:.2f}). The best accuracy any model can reach on these labels "
    f"lies between **{low:.1%}** and **{high:.1%}**:"
)
say(
    f"- *Lower end, the agreement itself ({low:.1%})*: if every disagreement is a headline "
    "with no single right label, nothing can match the label on it more often than the two "
    "passes match each other."
)
say(
    f"- *Upper end, the square root of the agreement (√{share:.3f} = {high:.1%})*: if every "
    "headline has one right label and each pass misses it independently with the same chance, "
    "two passes agree when both are right, so agreement = accuracy × accuracy."
)
say(
    "A third labelling pass is needed to tell which case holds and narrow the range. Where "
    "two passes differ, training counts the headline half for each label (`tone.shares`), "
    "and scoring uses the second pass, written under the same rule as the test set."
)

# %% [markdown]
# ## 4. Splits
#
# *How is the data divided so that no score is flattered by something the model has seen?*
#
# The split is by time, never at random: a model is always scored on headlines later
# than all it was trained on, which is how it is used. Choices are made on walk-forward
# blocks; the test set is read once, after every choice.

# %%
fig, ax = plt.subplots(figsize=(10, 2.4))
for row, name in enumerate(blocks.index):
    spans = [("validation", INK if name == "test" else ACCENT)]
    if name != "test":
        spans.insert(0, ("training", MUTED))
    for part, shade in spans:
        start, end = blocks.loc[name, f"{part} from"], blocks.loc[name, f"{part} to"]
        ax.barh(row, (end - start).days, left=start.tz_localize(None), color=shade, height=0.6)
ax.set_yticks(range(len(blocks)), blocks.index)
ax.invert_yaxis()
ax.set(title="Grey: trained on. Blue: validated on. Black: the test set")
plt.show()
caption(
    f"{tone.BLOCKS} walk-forward blocks of {tone.BLOCK} validation headlines each, and the test "
    f"set of {len(data.test)}; {report.window(data.labelled)} and {report.window(data.test)}."
)

# %%
dated = blocks.copy()
for column in [c for c in dated if " from" in c or " to" in c]:
    dated[column] = dated[column].map(lambda day: "" if pd.isna(day) else f"{day:%Y-%m-%d}")
display(tidy(dated))
caption("The same blocks as counts and dates. The test row has no training part.")

# %%
guards = tone.guards(data)
display(pd.Series(guards, name="count").to_frame())
caption(
    f"Leakage guards over {len(data.labelled):,} training and validation headlines, "
    f"{len(data.test):,} test headlines and {len(data.held_back):,} labelled headlines kept out."
)
say(
    f"**Found.** {sum(count == 0 for count in guards.values())} of {len(guards)} guards count "
    f"zero. The test period starts on {tone.TEST_FROM:%Y-%m-%d}; no training headline is dated "
    "on or after it."
)

# %% [markdown]
# ## 5. Features
#
# *What text does the model read?*
#
# A language model reads text directly, so the features are which text it is given.
# Stored summaries are cut at a fixed length, often mid-sentence, so only a summary's
# whole sentences are used (`dataset.whole_sentences`). The options were compared with
# one base model only, the social-media RoBERTa (`tone.choose_text`), so the text chosen
# is the one that suited that model.

# %%
headline, summary = "Gold Rises", "Bullion gained on the day. Analysts said the move could"
examples = {
    name: dataset.model_text(headline, summary, "Gold", **parts)
    for name, parts in tone.TEXTS.items()
}
display(pd.Series(examples, name="what the model reads").to_frame())
caption(f"The {len(tone.TEXTS)} input-text options, on one made-up headline and summary.")


# %%
def show_choice(found: dict | None, file: str, what: str) -> None:
    """One choice: the candidates with spread, the baselines, a chart, and the verdict."""
    if found is None:
        say(f"{what}: {report.not_available(file)}")
        return
    table = report.options(found)
    display(tidy(pd.concat([table.drop(columns="runs"), report.baseline_rows(data)])))
    if report.stored("baselines") is None:
        say(f"Baseline rows for the two existing models: {report.not_available('baselines')}")
    fig, ax = plt.subplots(figsize=(9, 0.45 * len(table) + 1.1))
    for place, name in enumerate(table.index[::-1]):
        runs = [run["loss"] for run in found[name]["runs"]]
        ax.scatter(runs, [place] * len(runs), color=MUTED, s=14, zorder=2)
        ax.scatter([np.mean(runs)], [place], color=ACCENT, s=70, zorder=3)
    ax.set_yticks(range(len(table)), table.index[::-1])
    ax.set(title=f"{what}: validation loss, each run (grey) and the mean (blue)")
    ax.grid(axis="y", visible=False)
    plt.show()
    runs = int(table["runs"].iloc[0])
    caption(
        f"{what}. Each candidate: {runs} runs ({tone.BLOCKS} blocks × {len(tone.CHOICE_SEEDS)} "
        f"seeds), {tone.BLOCK} validation headlines per block, validation "
        f"{blocks['validation from'].iloc[0]:%Y-%m-%d} to "
        f"{blocks.loc[f'block {tone.BLOCKS}', 'validation to']:%Y-%m-%d}. Baselines: mean of the blocks."
    )
    verdict = report.difference(found)
    say(
        f"**Found.** Lowest validation loss: *{verdict['winner']}*, ahead of "
        f"*{verdict['runner_up']}* by {verdict['gap']:.3f}. Two seeds of the same candidate on "
        f"the same block differ by {verdict['seed_spread']:.3f} on average, so this is "
        f"**{'a measurable difference' if verdict['measurable'] else 'no measurable difference'}**. "
        "The pipeline takes the lowest mean either way."
    )


show_choice(None if step1 is None else step1["options"], "step1_text", "Input text")

# %% [markdown]
# ## 6. Model selection
#
# *Which base model, and which training settings?*
#
# Each candidate is trained on every block with every choice seed, and the lowest mean
# validation loss wins (`tone.on_blocks`, `tone._winner`). The steps run in order and
# each starts from the last one's winner.
#
# **Validation figures lean optimistic.** In every run the block's validation headlines
# do two jobs: they pick which pass is kept, and they score the candidate. A score
# chosen as the best of several passes is better than the same model would get on new
# headlines. The lean is the same for every candidate, so it does not favour one over
# another, but the level of every validation figure in this notebook is flattered.

# %%
say(
    f"Every run uses at most {tone.START['epochs']} passes, stops when validation loss has not "
    f"improved for {tone.START['early_stopping_patience']}, and keeps the pass with the lowest "
    f"validation loss. Choice seeds: {list(tone.CHOICE_SEEDS)}."
)
display(report.dropout_defaults())
caption(
    f"The {len(tone.MODELS)} base models and the dropout each ships with, read from its "
    "configuration. A dropout setting of `None` below means this value."
)

# %%
show_choice(None if step2 is None else step2["options"], "step2_model", "Base model")

# %%
if step3 is None:
    say(f"Settings: {report.not_available('step3_settings')}")
else:
    for number, group in enumerate(step3["groups"], start=1):
        show_choice(group["options"], "step3_settings", f"Settings, group {number}")
    display(pd.Series(step3["settings"], name="value").to_frame())
    caption("The settings every later stage uses.")

# %% [markdown]
# ## 7. Training diagnostics
#
# *Does the model overfit, and where does it start?*
#
# The chosen recipe is trained once per final seed on the last block. Underfitting
# would show as high loss on training and validation alike. Overfitting shows as
# training loss still falling while validation loss rises. Training loss is always
# below validation loss, so a gap between them is not by itself overfitting; the sign is
# validation loss turning upwards.

# %%
if final is None:
    say(f"Training curves: {report.not_available('final')}")
else:
    stage = final["stages"][final["kept"]]
    fig, axes = plt.subplots(1, len(stage["passes"]), figsize=(13, 2.8), sharey=True)
    for ax, passes, kept, seed in zip(axes, stage["passes"], stage["kept"], tone.FINAL_SEEDS):
        frame = pd.DataFrame(passes).set_index("epoch")
        ax.plot(frame.index, frame["train_loss"], marker="o", color=MUTED, label="training")
        ax.plot(frame.index, frame["validation_loss"], marker="o", color=ACCENT, label="validation")
        ax.axvline(kept, color=INK, ls="--", lw=0.9)
        ax.set(title=f"seed {seed}", xlabel="pass", xticks=frame.index)
    axes[0].set_ylabel("loss")
    axes[0].legend()
    plt.show()
    caption(
        f"Loss by pass for the {len(tone.FINAL_SEEDS)} kept runs ({final['kept']}): "
        f"{final['train']:,} training headlines to {final['train_to'][:10]}, {final['validation']} "
        f"validation headlines to {final['validation_to'][:10]}. Dashed line: the pass kept."
    )

# %%
if final is not None:
    display(tidy(report.curves(final)))
    caption("The same runs as numbers. Training loss includes any label smoothing; validation loss does not.")
    fit = report.overfitting(final)
    say(
        f"**Found.** Validation loss is lowest at pass {fit['kept']} for the {fit['seeds']} "
        f"seeds. In {fit['rising']} of {fit['seeds']} runs it is higher at the last pass run "
        f"than at the kept pass, by {fit['mean_rise']:.3f} on average, while training loss "
        f"fell a further {fit['mean_training_fall']:.3f}: **overfitting starts at the pass "
        "after the kept one**, and those passes are discarded. At the kept pass training loss "
        f"is {fit['training_below_validation']:.3f} below validation loss on average. The kept "
        "pass is itself picked on these validation headlines, so its validation loss leans "
        "optimistic."
    )

# %% [markdown]
# ## 8. Ensemble and self-training
#
# *Does averaging the seeds help, and does adding unlabelled articles help?*
#
# **Ensemble.** The probabilities of the final seeds are averaged (`tone._five`).
# **Self-training.** The averaged model labels a pool of stored articles nobody has
# labelled; those it is sure enough about are added to the training headlines with the
# label it gave, and the seeds are trained again. The stage with the lower validation
# loss is kept (`tone.final`).

# %%
if final is None:
    say(f"Ensemble and self-training: {report.not_available('final')}")
else:
    display(tidy(report.stages(final)))
    caption(
        f"Last validation block: {final['validation']} headlines to {final['validation_to'][:10]}. "
        f"Seeds: {list(tone.FINAL_SEEDS)}."
    )
    pool = final["pool"]
    level = "none qualified" if pool["sure_level"] is None else f"{pool['sure_level']:.3f}"
    say(
        f"**Pool.** {pool['size']:,} unlabelled articles, {pool['from'][:10]} to {pool['to'][:10]}, "
        "drawn at random and none newer than the newest training headline. Confidence level for "
        f"\"sure\": {level} (the lowest at which the validation headlines kept are right "
        f"{tone.SURE_IS_RIGHT:.0%} of the time while keeping at least a fifth of them). "
        f"Pseudo-labels added: **{pool['added']:,}** {pool['added_mix']}."
    )
    say(f"**Found.** Kept: *{final['kept']}*, the stage with the lowest validation loss when averaged.")

# %% [markdown]
# ## 9. Calibration
#
# *When the model says how sure it is, is it right that often?*
#
# One number, a temperature, divides the model's scores before they become
# probabilities (`classification.fit_temperature`). It changes no answer, only how
# sure the model says it is. It is fitted on the last validation block and scored on the
# same block, so the improvement shown here is the most favourable case.

# %%
probabilities = None if final is None else report.validation_probabilities(data, final)
if probabilities is None:
    say(f"Calibration: {report.not_available('final')} (and `validation_final.npy`)")
else:
    truth, before, after = probabilities
    fig, ax = plt.subplots(figsize=(4.8, 3.6))
    ax.plot([1 / 3, 1], [1 / 3, 1], color=MUTED, ls="--", label="perfectly calibrated")
    for name, given, shade in (("before", before, INK), ("after", after, ACCENT)):
        table = report.reliability(truth, given)
        ax.plot(table["said"], table["right"], marker="o", color=shade, label=name)
    ax.set(xlabel="how sure it said it was", ylabel="how often it was right")
    ax.legend()
    plt.show()
    caption(f"Reliability before and after the temperature: {len(truth)} validation headlines.")
    display(tidy(report.reliability(truth, after)))
    caption(f"After the temperature, the same {len(truth)} headlines grouped by stated confidence.")
    say(
        f"**Found.** Temperature {final['temperature']:.2f}. The average distance between "
        f"stated confidence and accuracy goes from {report.calibration_gap(truth, before):.3f} "
        f"to {report.calibration_gap(truth, after):.3f}; validation loss ends at "
        f"{final['validation_after']['loss']:.3f} with accuracy unchanged at "
        f"{final['validation_after']['accuracy']:.1%}."
    )

# %% [markdown]
# ## 10. Test results
#
# *How good is the kept model on headlines it never saw, against the two bars?*
#
# The test set is scored once by `tone.test_once`, which stores the result and returns
# the stored result if called again. This notebook only reads that file.
#
# Because validation figures lean optimistic (sections 6, 7 and 9), the distance from
# validation to test is wider than it would be against an untouched validation set.
# That makes the "not overfitted" bar harder to pass, not easier.

# %%
if test is None:
    say(f"Test results: {report.not_available('test')}. Not yet run.")
else:
    scores = report.test_scores(test)
    display(tidy(scores))
    caption(
        f"Test set: {test['headlines']} headlines, {test['from'][:10]} to {test['to'][:10]}. "
        "95% range: Wilson interval."
    )
    check = test["comparison"]
    new, old = test["scores"]["new"], test["scores"]["in use"]
    say(
        f"**Bar 1, better than the model in use.** Accuracy {new['accuracy']:.1%} against "
        f"{old['accuracy']:.1%}. Only the new model was right on {check['only_second_right']} "
        f"headlines and only the model in use on {check['only_first_right']}; McNemar "
        f"p = {check['p_value']:.2g} (bar: below {tone.P_BELOW}). "
        f"**{'Pass' if test['bars']['better than the model in use'] else 'Fail'}.**"
    )
    say(
        f"**Bar 2, not overfitted.** Validation accuracy {test['validation']['accuracy']:.1%}, "
        f"test accuracy {new['accuracy']:.1%}: a gap of {test['accuracy_gap'] * 100:.1f} points "
        f"(bar: at most {tone.ACCURACY_GAP * 100:.0f}). Validation loss "
        f"{test['validation']['loss']:.3f}, test loss {new['loss']:.3f}: a gap of "
        f"{test['loss_gap']:.3f} (bar: at most {tone.LOSS_GAP:.2f}). "
        f"**{'Pass' if test['bars']['not overfitted'] else 'Fail'}.**"
    )
    say(
        f"Against the labels' own limit: test accuracy {new['accuracy']:.1%}, reachable range "
        f"{low:.1%} to {high:.1%} (section 3)."
    )

# %%
if test is not None:
    grid = pd.DataFrame(test["table"], index=LABELS, columns=LABELS)
    display(grid.rename_axis(index="the label", columns="the new model said"))
    caption(f"Confusion matrix, new model, {test['headlines']} test headlines.")
    display(tidy(pd.DataFrame(test["by_market"]).T))
    caption("Accuracy by market on the test set, the model in use beside the new one.")

# %% [markdown]
# ## 11. Error analysis
#
# *Where is the kept model wrong?* On the last validation block, since the test set is
# read only by `tone.test_once`.

# %%
errors = None if final is None else report.validation_errors(data, final)
if errors is None:
    say(f"Error analysis: {report.not_available('final')}")
else:
    display(errors["grid"])
    caption(f"Labels against answers, last validation block, {last_n} headlines.")
    display(tidy(errors["pairs"]))
    caption("Wrong answers only, by pair: the label, then what the model said.")
    display(tidy(errors["by market"]))
    caption("The same block by market.")
    top = errors["pairs"].iloc[0]
    label, said = errors["pairs"].index[0]
    worst = errors["by market"]["accuracy"].idxmin()
    say(
        f"**Found.** The commonest error is *{label}* called *{said}*: {int(top['headlines'])} "
        f"headlines, {top['share of all errors']:.0%} of all errors. The market with the lowest "
        f"validation accuracy is {worst} ({errors['by market'].loc[worst, 'accuracy']:.1%} of "
        f"{int(errors['by market'].loc[worst, 'headlines'])})."
    )

# %% [markdown]
# ## 12. Limitations and next steps
#
# *What should a reader not conclude from this?*

# %%
made = report.comparisons(
    {
        "input text": None if step1 is None else step1["options"],
        "base model": None if step2 is None else step2["options"],
        **(
            {}
            if step3 is None
            else {f"settings, group {i}": g["options"] for i, g in enumerate(step3["groups"], 1)}
        ),
    }
)
if len(made):
    display(tidy(made))
    caption("Every choice made so far: the winner's lead in validation loss beside the seed spread.")

# %%
unclear = 0 if not len(made) else int((made["verdict"] == "no measurable difference").sum())
say(
    f"- **The labels are written by a model.** Every label is by {', '.join(writers)}. Scores "
    "here are agreement with that labeller, not with a person."
)
say(
    f"- **The labels limit the score.** Reachable accuracy lies between {low:.1%} and "
    f"{high:.1%} (section 3). Narrowing it needs a third labelling pass; raising it needs "
    "firmer labels, for example keeping only headlines two passes agree on."
)
say(
    f"- **Seed noise is larger than most gaps between options.** In {unclear} of {len(made)} "
    "choices made so far, the winner's lead is smaller than the spread between two seeds."
)
say(
    f"- **The training set is small.** {len(data.labelled):,} labelled headlines; each "
    f"validation block is {tone.BLOCK}."
)
say(
    f"- **Gold is thin.** {gold_test} test headlines and "
    f"{int(agree.loc['Gold', 'headlines'])} in the agreement sample."
)
say(
    "- **Validation is used more than once** (to pick the pass, the candidate, the stage and "
    "the temperature), so validation figures lean optimistic. Only section 10 is untouched."
)
say(
    "- **Next steps.** No further model is tried on these labels (decision 102). Tone "
    "describes the news around a holding; it drives no forecast and no alert."
)

# %% [markdown]
# ## 13. Reproducibility
#
# *How is every figure above produced again?*
#
# ```
# uv sync --extra nlp
# uv run python backend/scripts/tone_draw.py            # draw headlines to label (already done)
# uv run python backend/scripts/tone_round4.py          # steps 1 to 6, stored as they finish
# uv run python backend/scripts/tone_round4.py test     # the test set, once
# uv run python backend/scripts/build_notebooks.py 04_news
# ```
#
# A step is repeated by deleting its file and running the script again. A training run is
# stored under a name made from its inputs, so the same inputs are never trained twice.

# %%
import torch
import transformers

facts = {
    "stored results": tone.OUT.as_posix(),
    "kept model files": tone.MODEL_DIR.as_posix(),
    "model in the app": finetune_job.MODEL_DIR.as_posix(),
    "choice seeds": list(tone.CHOICE_SEEDS),
    "final seeds": list(tone.FINAL_SEEDS),
    "draw seed for the pool and pseudo-labels": tone.DRAW_SEED,
    "test period starts": f"{tone.TEST_FROM:%Y-%m-%d}",
    "blocks": f"{tone.BLOCKS} of {tone.BLOCK}",
    "transformers": transformers.__version__,
    "torch": torch.__version__,
    **{f"result file: {name}": "stored" if report.stored(name) else "not available"
       for name in ("step1_text", "step2_model", "step3_settings", "final", "baselines", "test")},
}
display(pd.Series(facts, name="value").to_frame())
caption("Paths are relative to the repository. Code: `radar.pipelines.tone` and `tone_report`.")
