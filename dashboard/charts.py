"""Dependency-light Vega-Lite specifications for the Streamlit dashboard."""

from __future__ import annotations

from typing import Any


NAVY = "#102238"
BLUE = "#2E73FF"
TEAL = "#20B8A6"
AMBER = "#F4A340"
RED = "#E65B65"
GREY = "#8A98A8"
PURPLE = "#8067DC"


def _base(height: int = 300) -> dict[str, Any]:
    return {
        "height": height,
        "background": "#FFFFFF",
        "config": {
            "view": {"stroke": None},
            "axis": {
                "labelColor": "#44546A",
                "titleColor": NAVY,
                "gridColor": "#E8EDF3",
                "domainColor": "#AAB7C6",
                "tickColor": "#AAB7C6",
            },
            "legend": {"labelColor": "#44546A", "titleColor": NAVY},
            "title": {"color": NAVY},
        },
    }


def source_volume() -> dict[str, Any]:
    spec = _base(285)
    spec.update(
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 5, "color": BLUE},
            "encoding": {
                "x": {
                    "field": "source",
                    "type": "nominal",
                    "sort": "-y",
                    "title": None,
                    "axis": {"labelAngle": -20, "labelLimit": 130},
                },
                "y": {"field": "records", "type": "quantitative", "title": "Physical records"},
                "tooltip": [
                    {"field": "source", "type": "nominal", "title": "Source"},
                    {"field": "records", "type": "quantitative", "format": ",", "title": "Records"},
                ],
            },
        }
    )
    return spec


def count_bridge() -> dict[str, Any]:
    spec = _base(285)
    spec.update(
        {
            "layer": [
                {
                    "mark": {"type": "bar", "cornerRadiusEnd": 6},
                    "encoding": {
                        "y": {
                            "field": "stage",
                            "type": "nominal",
                            "sort": {"field": "order"},
                            "title": None,
                            "axis": {"labelLimit": 155},
                        },
                        "x": {"field": "count", "type": "quantitative", "title": "Records / identities", "scale": {"domain": [0, 440000]}},
                        "color": {"field": "stage", "type": "nominal", "legend": None, "scale": {"range": [NAVY, BLUE, TEAL, PURPLE]}},
                        "tooltip": [
                            {"field": "stage", "type": "nominal", "title": "Stage"},
                            {"field": "count", "type": "quantitative", "format": ",", "title": "Count"},
                        ],
                    },
                },
                {
                    "mark": {"type": "text", "align": "left", "dx": 7, "fontWeight": 700, "color": NAVY},
                    "encoding": {
                        "y": {"field": "stage", "type": "nominal", "sort": {"field": "order"}},
                        "x": {"field": "count", "type": "quantitative"},
                        "text": {"field": "count", "type": "quantitative", "format": ","},
                    },
                },
            ]
        }
    )
    return spec


def decision_donut() -> dict[str, Any]:
    spec = _base(285)
    spec.update(
        {
            "mark": {"type": "arc", "innerRadius": 68, "outerRadius": 112, "stroke": "white", "strokeWidth": 2},
            "encoding": {
                "theta": {"field": "pairs", "type": "quantitative"},
                "color": {
                    "field": "decision",
                    "type": "nominal",
                    "scale": {"domain": ["Auto-merge", "Human review", "Leave separate"], "range": [TEAL, AMBER, GREY]},
                    "legend": {"orient": "bottom", "title": None},
                },
                "tooltip": [
                    {"field": "decision", "type": "nominal", "title": "Decision"},
                    {"field": "pairs", "type": "quantitative", "format": ",", "title": "Pairs"},
                ],
            },
        }
    )
    return spec


def model_comparison() -> dict[str, Any]:
    spec = _base(320)
    spec.update(
        {
            "transform": [
                {"fold": ["auto_recall", "assisted_recall"], "as": ["metric", "value"]},
                {"calculate": "datum.metric === 'auto_recall' ? 'Auto recall' : 'Assisted recall'", "as": "metric_label"},
            ],
            "mark": {"type": "bar", "cornerRadiusEnd": 4},
            "encoding": {
                "x": {"field": "model", "type": "nominal", "title": None},
                "xOffset": {"field": "metric_label"},
                "y": {"field": "value", "type": "quantitative", "title": "Validation recall", "axis": {"format": ".0%"}, "scale": {"domain": [0.5, 0.92]}},
                "color": {"field": "metric_label", "type": "nominal", "scale": {"range": [BLUE, TEAL]}, "legend": {"title": None, "orient": "bottom"}},
                "opacity": {"condition": {"test": "datum.false_auto_merges === 0", "value": 1}, "value": 0.45},
                "tooltip": [
                    {"field": "model", "type": "nominal", "title": "Model"},
                    {"field": "metric_label", "type": "nominal", "title": "Metric"},
                    {"field": "value", "type": "quantitative", "format": ".4%", "title": "Value"},
                    {"field": "precision", "type": "quantitative", "format": ".4%", "title": "Auto precision"},
                    {"field": "false_auto_merges", "type": "quantitative", "title": "False auto-merges"},
                ],
            },
        }
    )
    return spec


def candidate_reduction() -> dict[str, Any]:
    spec = _base(245)
    spec.update(
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 5},
            "encoding": {
                "y": {"field": "stage", "type": "nominal", "sort": ["All possible pairs", "Blocked candidates"], "title": None},
                "x": {"field": "pairs", "type": "quantitative", "scale": {"type": "log"}, "title": "Pair count (log scale)"},
                "color": {"field": "stage", "type": "nominal", "legend": None, "scale": {"range": [GREY, BLUE]}},
                "tooltip": [
                    {"field": "stage", "type": "nominal", "title": "Stage"},
                    {"field": "pairs", "type": "quantitative", "format": ",", "title": "Pairs"},
                ],
            },
        }
    )
    return spec


def business_range() -> dict[str, Any]:
    spec = _base(185)
    spec.update(
        {
            "layer": [
                {
                    "mark": {"type": "rule", "strokeWidth": 12, "strokeCap": "round", "color": "#C8D4E3"},
                    "encoding": {"x": {"field": "lower", "type": "quantitative", "scale": {"domain": [285000, 410000]}, "title": "Distinct-person count"}, "x2": {"field": "upper"}, "y": {"value": 72}},
                },
                {
                    "mark": {"type": "point", "filled": True, "size": 220, "color": PURPLE},
                    "encoding": {"x": {"field": "recommended", "type": "quantitative"}, "y": {"value": 72}, "tooltip": [{"field": "recommended", "format": ",", "title": "Recommended"}]},
                },
                {
                    "mark": {"type": "point", "filled": True, "shape": "diamond", "size": 135, "color": TEAL},
                    "encoding": {"x": {"field": "finance", "type": "quantitative"}, "y": {"value": 72}, "tooltip": [{"field": "finance", "format": ",", "title": "Finance reference"}]},
                },
                {
                    "mark": {"type": "point", "filled": True, "shape": "triangle", "size": 150, "color": AMBER},
                    "encoding": {"x": {"field": "marketing", "type": "quantitative"}, "y": {"value": 72}, "tooltip": [{"field": "marketing", "format": ",", "title": "Marketing reference"}]},
                },
            ]
        }
    )
    return spec


def source_pair_recall() -> dict[str, Any]:
    spec = _base(360)
    spec.update(
        {
            "transform": [
                {"fold": ["auto_recall", "assisted_recall"], "as": ["metric", "value"]},
                {"calculate": "datum.metric === 'auto_recall' ? 'Auto recall' : 'Assisted recall'", "as": "metric_label"},
            ],
            "mark": {"type": "bar", "cornerRadiusEnd": 3},
            "encoding": {
                "y": {"field": "source_pair", "type": "nominal", "sort": {"field": "true_matches", "order": "descending"}, "title": None},
                "x": {"field": "value", "type": "quantitative", "title": "Frozen-test recall", "axis": {"format": ".0%"}, "scale": {"domain": [0, 1]}},
                "yOffset": {"field": "metric_label"},
                "color": {"field": "metric_label", "type": "nominal", "scale": {"range": [BLUE, TEAL]}, "legend": {"title": None, "orient": "bottom"}},
                "tooltip": [
                    {"field": "source_pair", "type": "nominal", "title": "Source pair"},
                    {"field": "metric_label", "type": "nominal", "title": "Metric"},
                    {"field": "value", "type": "quantitative", "format": ".4%", "title": "Recall"},
                    {"field": "true_matches", "type": "quantitative", "format": ",", "title": "True matches"},
                ],
            },
        }
    )
    return spec


def cluster_distribution() -> dict[str, Any]:
    spec = _base(280)
    spec.update(
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 4, "color": TEAL},
            "encoding": {
                "x": {"field": "component_size", "type": "ordinal", "title": "Records in component"},
                "y": {"field": "components", "type": "quantitative", "title": "Components", "scale": {"type": "log"}},
                "tooltip": [
                    {"field": "component_size", "type": "ordinal", "title": "Component size"},
                    {"field": "components", "type": "quantitative", "format": ",", "title": "Components"},
                    {"field": "status", "type": "nominal", "title": "Status"},
                ],
            },
        }
    )
    return spec


def contribution_chart() -> dict[str, Any]:
    spec = _base(300)
    spec.update(
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 3},
            "encoding": {
                "y": {"field": "feature", "type": "nominal", "sort": "-x", "title": None, "axis": {"labelLimit": 320}},
                "x": {"field": "contribution", "type": "quantitative", "title": "Logit contribution"},
                "color": {"condition": {"test": "datum.contribution >= 0", "value": TEAL}, "value": RED},
                "tooltip": [
                    {"field": "feature", "type": "nominal", "title": "Feature"},
                    {"field": "contribution", "type": "quantitative", "format": ".4f", "title": "Contribution"},
                ],
            },
        }
    )
    return spec
