"""Dashboard styling, data-mode disclaimer banners, and freshness indicators."""

from __future__ import annotations

from typing import Any

import streamlit as st

# Cohesive forest-research color palette
PALETTE = {
    "forest": "#1B5E3A",
    "forest_soft": "#2E7D52",
    "sage": "#5C8D73",
    "reduction": "#C2512F",
    "increase": "#1F7A6B",
    "neutral": "#64748B",
    "amber": "#B45309",
    "morning": "#D97706",
    "afternoon": "#1E6091",
    "weekday": "#2B6CB0",
    "weekend": "#B83253",
}

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#FFFFFF",
    font=dict(family="Inter, system-ui, -apple-system, sans-serif", color="#1E293B", size=12),
    margin=dict(l=16, r=16, t=44, b=16),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
)


def inject_custom_css() -> None:
    """Apply clean, responsive editorial-analytics styling."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
            max-width: 1320px;
        }
        div[data-testid="stMetric"] {
            background: #FFFFFF;
            border: 1px solid #DDE5DF;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            box-shadow: 0 1px 2px rgba(16, 36, 24, 0.04);
        }
        div[data-testid="stMetricLabel"] p {
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            color: #4A5D52 !important;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.55rem !important;
            font-weight: 700 !important;
            color: #13251B !important;
        }
        .csm-header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            padding: 1rem 1.25rem;
            background: linear-gradient(135deg, #163C28 0%, #1E5638 100%);
            color: #F8FAF8;
            border-radius: 12px;
            margin-bottom: 0.9rem;
        }
        .csm-header h1 {
            margin: 0;
            font-size: 1.35rem;
            font-weight: 700;
            color: #FFFFFF;
            letter-spacing: -0.01em;
        }
        .csm-header p {
            margin: 0.2rem 0 0 0;
            font-size: 0.85rem;
            color: #D2E4D9;
        }
        .csm-pill {
            display: inline-block;
            padding: 0.28rem 0.68rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            white-space: nowrap;
        }
        .csm-pill-readonly {
            background: rgba(255, 255, 255, 0.16);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.28);
        }
        .csm-banner-demo {
            background: #FFFBEB;
            border: 1px solid #F59E0B;
            border-left: 5px solid #D97706;
            color: #78350F;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.87rem;
            margin-bottom: 0.85rem;
        }
        .csm-banner-live {
            background: #ECFDF5;
            border: 1px solid #6EE7B7;
            border-left: 5px solid #059669;
            color: #064E3B;
            padding: 0.7rem 1rem;
            border-radius: 8px;
            font-size: 0.86rem;
            margin-bottom: 0.85rem;
        }
        .csm-banner-stale {
            background: #FEF2F2;
            border: 1px solid #FCA5A5;
            border-left: 5px solid #DC2626;
            color: #7F1D1D;
            padding: 0.68rem 1rem;
            border-radius: 8px;
            font-size: 0.85rem;
            margin-bottom: 0.85rem;
        }
        .csm-note {
            background: #F1F5F3;
            border-left: 4px solid #1B5E3A;
            padding: 0.65rem 0.95rem;
            border-radius: 6px;
            font-size: 0.84rem;
            color: #26382E;
            margin: 0.5rem 0 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_header(
    *,
    page_title: str,
    page_subtitle: str,
    is_demo_mode: bool,
    freshness: dict[str, Any],
) -> None:
    """Render top page banner, explicit LIVE vs DEMO indicator, and staleness warning."""
    st.markdown(
        f"""
        <div class="csm-header">
            <div>
                <h1>{page_title}</h1>
                <p>{page_subtitle}</p>
            </div>
            <div>
                <span class="csm-pill csm-pill-readonly">READ-ONLY RESEARCH MONITOR · safari.corbettgov.org</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_demo_mode:
        last_str = freshness.get("last_success_at") or "None"
        st.markdown(
            f"""
            <div class="csm-banner-demo">
                <strong>DEMONSTRATION / SAMPLE TEST DATA MODE</strong> — Displaying isolated,
                clearly labeled synthetic test records from <code>data/demo_corbett_monitor.db</code>
                (never mixed with live data). Latest sample run: <strong>{last_str}</strong>.
                Switch to <strong>Live Database</strong> in the sidebar to inspect or run genuine
                portal monitoring.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if not freshness["has_successful_run"]:
            st.markdown(
                """
                <div class="csm-banner-stale">
                    <strong>LIVE DATABASE — NO LIVE SNAPSHOTS COLLECTED YET</strong> —
                    <code>data/corbett_monitor.db</code> contains the initialized schema and all 8 official
                    Corbett Tiger Reserve zones (zero fake records). Live collection requires running the
                    Playwright inspector/collector from an authorized local browser with genuine location
                    permission. See <strong>Collection Monitoring</strong> for run controls and compliance status.
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif freshness["is_stale"]:
            st.markdown(
                f"""
                <div class="csm-banner-stale">
                    <strong>STALE DATA WARNING</strong> — Last successful live observation was at
                    <strong>{freshness['last_success_at']}</strong> ({freshness['status_label']}).
                    Stored values below reflect that historical timestamp, NOT current live availability.
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="csm-banner-live">
                    <strong>LIVE DATABASE ACTIVE</strong> — Last successful observation:
                    <strong>{freshness['last_success_at']}</strong> ({freshness['status_label']}).
                </div>
                """,
                unsafe_allow_html=True,
            )
