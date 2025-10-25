#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import sys
from typing import Optional, Sequence
import pandas as pd
import matplotlib
# Use a non-interactive backend automatically if no display (common on headless Pi)
if not os.environ.get("DISPLAY"):
    matplotlib.use("Agg")  # noqa: E402
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


DEFAULT_PRESSURE_COL = "pressure_hPa"
DEFAULT_TEMP_COL = "temperature_C"
DEFAULT_TIME_COL = "timestamp"


def load_data(
    path: str,
    time_col: str,
    columns: Sequence[str],
    tz_localize: Optional[str] = None,
) -> pd.DataFrame:
    usecols = list({time_col, *columns})
    try:
        df = pd.read_csv(
            path,
            usecols=usecols,
            parse_dates=[time_col],
        )
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {path}")
    except ValueError as e:
        sys.exit(f"Error reading CSV ({path}): {e}")

    if df.empty:
        sys.exit("Error: dataset is empty.")

    # Sort & drop duplicate timestamps
    df = df.sort_values(time_col)
    df = df.drop_duplicates(subset=time_col)

    if tz_localize and df[time_col].dt.tz is None:
        df[time_col] = df[time_col].dt.tz_localize(tz_localize)

    return df.set_index(time_col)


def maybe_filter_ranges(df: pd.DataFrame, pressure_col: str, temp_col: str) -> pd.DataFrame:
    # Basic physical sanity filters (BMP180 typical ranges)
    mask = (
        (df[pressure_col].between(850, 1100, inclusive="both")) &
        (df[temp_col].between(-40, 85, inclusive="both"))
    )
    return df[mask]


def resample_df(
    df: pd.DataFrame,
    rule: Optional[str],
    agg: str = "mean",
) -> pd.DataFrame:
    if not rule:
        return df
    if rule:
        return getattr(df.resample(rule), agg)()
    return df


def add_rolling(df: pd.DataFrame, cols: Sequence[str], window: Optional[int]) -> pd.DataFrame:
    if not window or window <= 1:
        return df
    for c in cols:
        roll_name = f"{c}_roll{window}"
        df[roll_name] = df[c].rolling(window, min_periods=max(1, window // 3)).mean()
    return df


def build_plot(
    df: pd.DataFrame,
    pressure_col: str,
    temp_col: str,
    show_rolling: bool,
    figsize=(11, 5),
    title: Optional[str] = None,
    date_fmt: str = "%H:%M",
):
    fig, ax_p = plt.subplots(figsize=figsize)

    ax_t = ax_p.twinx()

    pressure_line, = ax_p.plot(
        df.index,
        df[pressure_col],
        color="#1f77b4",
        label="Pressure (hPa)",
        linewidth=1.4,
    )
    temp_line, = ax_t.plot(
        df.index,
        df[temp_col],
        color="#d62728",
        label="Temperature (°C)",
        linewidth=1.2,
    )

    # Rolling series (if present)
    if show_rolling:
        for col, base_color in ((pressure_col, "#1f77b4"), (temp_col, "#d62728")):
            roll_col = next((c for c in df.columns if c.startswith(col + "_roll")), None)
            if roll_col:
                target_ax = ax_p if col == pressure_col else ax_t
                target_ax.plot(
                    df.index,
                    df[roll_col],
                    color=base_color,
                    linewidth=2.0,
                    alpha=0.5,
                    label=f"{roll_col}",
                )

    ax_p.set_xlabel("Time")
    ax_p.set_ylabel("Pressure (hPa)", color=pressure_line.get_color())
    ax_t.set_ylabel("Temperature (°C)", color=temp_line.get_color())

    if not title:
        if len(df.index) > 1:
            title = f"Sensor data {df.index.min()} → {df.index.max()}"
        else:
            title = "Sensor data"
    ax_p.set_title(title)

    # Date formatting
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    formatter.formats[3] = date_fmt  # hour-level
    ax_p.xaxis.set_major_locator(locator)
    ax_p.xaxis.set_major_formatter(formatter)

    ax_p.grid(True, alpha=0.25)

    # Compose legend from both axes
    lines = ax_p.get_lines() + ax_t.get_lines()
    labels = [l.get_label() for l in lines]
    ax_p.legend(lines, labels, loc="upper left", framealpha=0.85)

    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def parse_args():
    p = argparse.ArgumentParser(description="Plot BMP180 (pressure & temperature) log.")
    p.add_argument("-i", "--input", default="env_log.csv", help="Input CSV file.")
    p.add_argument("--pressure-col", default=DEFAULT_PRESSURE_COL)
    p.add_argument("--temp-col", default=DEFAULT_TEMP_COL)
    p.add_argument("--time-col", default=DEFAULT_TIME_COL)
    p.add_argument("--resample", default=None, help="Pandas resample rule (e.g. 5T, 15T, 1H).")
    p.add_argument("--agg", default="mean", choices=("mean", "median", "max", "min"))
    p.add_argument("--rolling", type=int, default=0, help="Rolling window (points). 0 disables.")
    p.add_argument("--filter-phys", action="store_true", help="Filter out-of-range values.")
    p.add_argument("--save", metavar="PATH", help="Save figure to file instead of (or in addition to) showing.")
    p.add_argument("--dpi", type=int, default=140)
    p.add_argument("--no-show", action="store_true", help="Do not display window even if display available.")
    p.add_argument("--timezone", default=None, help="Localize naive timestamps (e.g. Europe/Berlin).")
    p.add_argument("--style", default="seaborn-v0_8", help="Matplotlib style (e.g. seaborn-v0_8, default, fast).")
    p.add_argument("--date-fmt", default="%H:%M", help="Hour tick label format.")
    return p.parse_args()


def main():
    args = parse_args()

    # Style
    try:
        plt.style.use(args.style)
    except OSError:
        print(f"Warning: style '{args.style}' not found, using default.", file=sys.stderr)

    df = load_data(
        args.input,
        time_col=args.time_col,
        columns=[args.pressure_col, args.temp_col],
        tz_localize=args.timezone,
    )

    missing = [c for c in (args.pressure_col, args.temp_col) if c not in df.columns]
    if missing:
        sys.exit(f"Error: missing required columns in CSV: {missing}")

    if args.filter_phys:
        before = len(df)
        df = maybe_filter_ranges(df, args.pressure_col, args.temp_col)
        removed = before - len(df)
        if removed:
            print(f"Filtered {removed} out-of-range rows.")

    df = resample_df(df, args.resample, args.agg)
    df = add_rolling(df, [args.pressure_col, args.temp_col], args.rolling if args.rolling > 1 else None)

    fig = build_plot(
        df,
        pressure_col=args.pressure_col,
        temp_col=args.temp_col,
        show_rolling=args.rolling > 1,
        date_fmt=args.date_fmt,
    )

    if args.save:
        fig.savefig(args.save, dpi=args.dpi)
        print(f"Saved: {args.save}")

    if (not args.no_show) and matplotlib.get_backend().lower() != "agg":
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
