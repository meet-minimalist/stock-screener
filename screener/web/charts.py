from __future__ import annotations

import base64
import logging

from screener.reports.rrg_chart import build_rrg_chart
from screener.screeners.sector_rotation import compute_rrg_tails

logger = logging.getLogger(__name__)


def render_rrg_data_uri(start_date: str, end_date: str, interval: str = "1d",
                        rrg_window: int = 63, tail_weeks: int = 12,
                        cache_dir: str = "data/yfinance_cache") -> str | None:
    """Render the RRG chart to a base64 PNG data URI (self-contained, no CDN).

    Returns None if the chart can't be produced (kaleido missing or no data) so
    the page still renders without it.
    """
    try:
        tails = compute_rrg_tails(start_date, end_date, interval=interval,
                                  rrg_window=rrg_window, tail_weeks=tail_weeks,
                                  cache_dir=cache_dir)
        if not tails:
            return None
        fig = build_rrg_chart(tails)
        fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
        png = fig.to_image(format="png", width=1000, height=760, scale=2)
    except Exception as exc:
        logger.warning("Could not render RRG chart: %s", exc)
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
