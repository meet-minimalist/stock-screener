"""Presentation layer: turn a pipeline result into a static, interactive site.

Kept separate from the compute side (scoring/screens) so rendering can change
without touching the pipeline. ``build_site`` produces the full standalone page
(GitHub Pages) and its inner body (Claude Artifact preview).
"""

from screener.web.charts import render_rrg_data_uri
from screener.web.site import build_site, build_site_body, wrap_page

__all__ = ["build_site", "build_site_body", "wrap_page", "render_rrg_data_uri"]
