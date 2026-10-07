"""One look for every notebook: colours, chart defaults and table formatting.

A notebook calls `use_style()` once at the top. Nothing here does analysis.
"""

INK, MUTED, GOOD, BAD, ACCENT = "#1c2030", "#8a8fa3", "#2f9e6e", "#d9534f", "#1f9bb8"
BUY, SELL = "#2f9e6e", "#d9534f"


def use_style() -> None:
    """Set the chart and table defaults. Imports are local so that the app, which
    never draws a chart, does not load matplotlib."""
    import matplotlib.pyplot as plt
    import pandas as pd

    plt.rcParams.update(
        {
            "figure.figsize": (10, 3.6),
            "figure.dpi": 110,
            "font.size": 9.5,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titlelocation": "left",
            "axes.titleweight": "bold",
            "axes.titlesize": 10.5,
            "axes.edgecolor": MUTED,
            "text.color": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "legend.frameon": False,
        }
    )
    pd.set_option("display.float_format", lambda value: f"{value:,.2f}")
    pd.set_option("display.width", 120)
    pd.set_option("display.max_columns", 12)
