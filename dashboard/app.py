"""Kestrel Identity Resolution Control Room."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard import charts
from dashboard.data_loader import DashboardDataError, load_dashboard_data, score_selected_model


ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(
    page_title="Kestrel Identity Control Room",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --navy:#102238; --blue:#2E73FF; --teal:#20B8A6; --amber:#F4A340; --paper:#F6F8FB; }
    .stApp { background: linear-gradient(180deg, #F7F9FC 0%, #FFFFFF 45%); color:#102238; }
    [data-testid="stSidebar"] { background: #102238; }
    [data-testid="stSidebar"] * { color: #F3F7FB !important; }
    [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3,
    [data-testid="stMain"] p, [data-testid="stMain"] label { color:#102238 !important; }
    [data-testid="stMetric"] { background:white; border:1px solid #E1E8F0; border-radius:14px; padding:18px; box-shadow:0 5px 18px rgba(16,34,56,.06); }
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * { color:#66758A !important; }
    [data-testid="stMetricLabel"] p { white-space:normal !important; overflow:visible !important; text-overflow:clip !important; line-height:1.2 !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * { color:#102238 !important; }
    .hero { background:linear-gradient(120deg,#102238,#173C66); color:white; padding:28px 32px; border-radius:18px; margin-bottom:22px; box-shadow:0 14px 32px rgba(16,34,56,.16); }
    .hero h1 { color:white !important; margin:0 0 7px 0; font-size:2.15rem; }
    .hero p { color:#DCE8F4 !important; margin:0; max-width:900px; }
    .badge { display:inline-block; background:#DDF7F2; color:#087B6E; font-weight:700; font-size:.72rem; letter-spacing:.08em; padding:5px 9px; border-radius:99px; margin-bottom:12px; }
    .callout { background:white; border-left:5px solid #2E73FF; padding:16px 18px; border-radius:8px; margin:10px 0 18px 0; box-shadow:0 4px 14px rgba(16,34,56,.05); }
    .callout, .callout * { color:#102238 !important; }
    .warning { background:#FFF8E8; border-left-color:#F4A340; }
    .success { background:#EAF9F5; border-left-color:#20B8A6; }
    .verdict { text-align:center; padding:22px; border-radius:14px; color:white; font-weight:800; font-size:1.25rem; margin:8px 0; }
    .smallprint { color:#6B7A8F; font-size:.82rem; }
    [data-testid="stVegaLiteChart"] { background:#FFFFFF; border:1px solid #E1E8F0; border-radius:14px; padding:10px; box-shadow:0 4px 14px rgba(16,34,56,.04); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def snapshot(root: str) -> dict:
    return load_dashboard_data(Path(root))


def chart(data: list[dict], spec: dict, key: str) -> None:
    st.vega_lite_chart(data=data, spec=spec, width="stretch", theme=None, key=key)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><span class="badge">SYNTHETIC EVALUATION</span><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def metric_row(items: list[tuple[str, str, str | None, str]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value, help_text, formula) in zip(columns, items):
        with column:
            st.metric(label, value, help=help_text)
            with st.expander("Formula / definition"):
                st.markdown(formula)


def how_to_read_numbers() -> None:
    st.markdown(
        """
        <div class="callout">
        <b>How to read these numbers</b><br>
        <b>Record:</b> one physical row in a source system. &nbsp;
        <b>Pair:</b> two records compared as a possible match. &nbsp;
        <b>Cluster / identity:</b> records connected by accepted matches after transitivity and Rule 1. &nbsp;
        <b>People / customers:</b> the planning estimate after observable non-customer traffic is removed and unresolved matches are modelled. It is not a directly observed production total.
        </div>
        """,
        unsafe_allow_html=True,
    )


try:
    data = snapshot(str(ROOT))
except DashboardDataError as exc:
    st.error(f"Dashboard data contract failed: {exc}")
    st.stop()


st.sidebar.markdown("## Kestrel Control Room")
st.sidebar.caption("Identity resolution · Phase 14A")
page = st.sidebar.radio(
    "View",
    ["Executive brief", "Technical audit", "MCT decision lab", "Methods & limits"],
)
st.sidebar.markdown("---")
st.sidebar.markdown("**Decision policy**")
st.sidebar.caption("MCT ≥ 0.88 · Auto-merge")
st.sidebar.caption("0.62 ≤ MCT < 0.88 · Review")
st.sidebar.caption("MCT < 0.62 · Separate")
st.sidebar.markdown("---")
st.sidebar.caption("Read-only · Aggregate artifacts only")

executive = data["executive"]

if page == "Executive brief":
    hero(
        "How many customers does Kestrel have?",
        "Marketing sees accounts. Finance sees people. This view connects 420,000 source records to a safety-first customer estimate.",
    )
    how_to_read_numbers()
    metric_row(
        [
            ("Source records", f"{executive['source_records']:,}", "Physical rows across five source systems", "120,000 app + 80,000 store + 80,000 ticketing + 50,000 subscriptions + 90,000 social = **420,000 records**."),
            ("Operational identities", f"{executive['operational_identities']:,}", "Rule 1-safe selected clusters before traffic exclusions", "420,000 source records - 77,100 records collapsed by accepted MCT merges = **342,900 Rule 1-safe identities**."),
            ("Recommended customers", f"{executive['recommended_customers']:,}", "Median candidate-resolvable aggregate scenario", "333,000 customer-like identities - median 17,823 additional identities resolved in the aggregate scenario = **315,177**. This scenario does not authorize operational merges."),
        ]
    )
    metric_row(
        [
            ("Planning range—not a confidence interval", f"{executive['range_lower']:,}–{executive['range_upper']:,}", "A conservative sensitivity interval, not a statistical confidence interval", "Upper = 342,900 - 8,400 automation clusters - 1,500 internal-QA clusters = **333,000**. Lower = 333,000 - 23,656 recoverable links not merged - 10,105 unrecoverable links = **299,239**."),
            ("Review pairs", f"{executive['review_pairs']:,}", "Physical candidate pairs requiring human review", "Count of scored candidate pairs with **0.62 ≤ MCT < 0.88** = **20,560**."),
            ("Frozen-test false auto-merges", f"{executive['false_auto_merges']:,}", "Observed on held-out synthetic data; not a production guarantee", "False positives among 29,124 frozen-test pairs assigned MCT ≥ 0.88 = **0 observed false auto-merges**."),
        ]
    )
    st.markdown(
        '<div class="callout success"><b>Recommendation.</b> Use 315,177 as the planning estimate and 299,239–333,000 as the planning sensitivity range—not a confidence interval. Keep 342,900 as the operational identity count; the aggregate estimate does not authorize below-threshold merges.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="callout"><b>Why the upper endpoint is 333,000</b><br><span style="font-size:1.15rem;font-weight:750">342,900 operational identities &minus; 8,400 automation clusters &minus; 1,500 internal-QA clusters = 333,000 customer-like identities</span></div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("The count journey")
        chart(data["count_bridge"], charts.count_bridge(), "count-bridge")
    with right:
        st.subheader("Where the records came from")
        chart(data["sources"], charts.source_volume(), "source-volume")

    st.subheader("A range, not false certainty")
    range_data = [
        {
            "lower": executive["range_lower"],
            "upper": executive["range_upper"],
            "recommended": executive["recommended_customers"],
            "finance": 300000,
            "marketing": 400000,
        }
    ]
    chart(range_data, charts.business_range(), "business-range")
    st.caption("Purple: recommended · teal diamond: Finance reference · amber triangle: Marketing reference · grey bar: planning sensitivity range")

    st.subheader("Operational consequence")
    workload = data["review_workload"]
    metric_row(
        [
            ("Unique cluster-pair reviews", f"{workload['unique_review_cluster_pairs']:,}", None, "Count of distinct unordered operational-cluster pairs represented by the 20,560 physical review edges = **15,247**."),
            ("2-minute scenario", f"{workload['two_minute_hours']:.1f} hours", "Planning assumption", "20,560 physical review pairs × 2 minutes ÷ 60 = **685.3 reviewer-hours**."),
            ("5-minute scenario", f"{workload['five_minute_hours']:.1f} hours", "Planning assumption", "20,560 physical review pairs × 5 minutes ÷ 60 = **1,713.3 reviewer-hours**."),
        ]
    )
    st.markdown(
        '<div class="callout warning"><b>Risk statement.</b> A missed match can duplicate communication. A false merge can expose another person’s order, ticket, subscription or address. Merge precision therefore outranks raw match volume.</div>',
        unsafe_allow_html=True,
    )

elif page == "Technical audit":
    hero(
        "Evidence before algorithms",
        "Inspect how profiling, Rule 2, blocking, model selection and capped transitivity control false-merge risk.",
    )
    how_to_read_numbers()
    st.subheader("Candidate reduction")
    blocking = data["blocking"]
    metric_row(
        [
            ("All possible pairs", f"{blocking['all_possible_pairs']:,}", None, "For 420,000 records: 420,000 × 419,999 ÷ 2 = **88,199,790,000 unordered pairs**."),
            ("Candidates scored", f"{blocking['candidate_pairs']:,}", None, "Count of unique unordered record pairs emitted by the Rule 2-safe blocking rules = **204,547**."),
            ("Comparison workload reduction", f"{blocking['candidate_reduction_percentage']:.6f}%", None, "(1 - 204,547 ÷ 88,199,790,000) × 100 = **99.999768% fewer comparisons**."),
        ]
    )
    metric_row(
        [
            ("Normalized Rule 2 values", f"{blocking['rule2_values']:,}", "Values occurring on more than 40 rows", "Count of distinct normalized identifier values with physical-row frequency > 40 = **2,057**. Each receives zero matching weight."),
            ("Recoverable blocking recall", f"{blocking['recoverable_blocking_recall']:.4%}", "Definition: recoverable true links retained as candidates ÷ all recoverable true links", "88,155 recoverable canonical true links retained ÷ 88,155 recoverable canonical true links = **100%**. The 10,105 discarded links had no usable blocking evidence and are excluded from this denominator."),
        ]
    )
    chart(
        [
            {"stage": "All possible pairs", "pairs": blocking["all_possible_pairs"]},
            {"stage": "Blocked candidates", "pairs": blocking["candidate_pairs"]},
        ],
        charts.candidate_reduction(),
        "candidate-reduction",
    )
    st.caption(f"All {blocking['recoverable_links']:,} recoverable canonical links were retained; {blocking['discarded_links']:,} true links were discarded before scoring because no usable block recovered them.")

    left, right = st.columns([1.35, 1])
    with left:
        st.subheader("Model selection on validation")
        chart(data["models"], charts.model_comparison(), "model-comparison")
        st.caption("Hover definitions: auto recall = true matches auto-merged ÷ all true matches; assisted recall = true matches auto-merged or sent to review ÷ all true matches.")
        st.caption("Faded bars identify a model with a validation false auto-merge. Frozen test was not used for selection.")
    with right:
        st.subheader("Full MCT decisions")
        chart(data["decisions"], charts.decision_donut(), "decision-donut")

    st.subheader("Cluster-level safety after transitivity")
    clustering = data["clustering"]
    metric_row(
        [
            ("Implied merged pairs", f"{clustering['implied_merged_pairs']:,}", None, "Sum of n × (n - 1) ÷ 2 across every accepted transitive component = **99,372 record pairs**."),
            ("False merged pairs", f"{clustering['false_merged_pairs']:,}", "Observed in synthetic evaluation", "Accepted implied record pairs whose hidden person IDs differ = **0** on this synthetic evaluation."),
            ("Mixed-person components", f"{clustering['mixed_person_components']:,}", None, "Accepted components containing more than one hidden person ID = **0** on this synthetic evaluation."),
        ]
    )
    metric_row(
        [
            ("Largest component", f"{clustering['largest_component']}", "Rule 1 maximum accepted size is 12 physical records", f"Maximum physical-record count among proposed components = **{clustering['largest_proposed_component']}**, which is within the Rule 1 cap of {clustering['rule1_maximum']}."),
            ("Quarantined components", f"{clustering['quarantined_components']:,}", None, "Count of proposed transitive components with 13 or more physical records, rejected in full = **0**."),
        ]
    )
    rule1_result = "did not need to fire" if clustering["quarantined_components"] == 0 else "quarantined oversized components"
    st.markdown(
        f'<div class="callout success"><b>Rule 1 was applied; it {rule1_result}.</b><br>{clustering["auto_merge_edges"]:,} auto-merge edges were unioned transitively into {clustering["proposed_components"]:,} proposed components. The largest contained {clustering["largest_proposed_component"]} records; the maximum accepted size is {clustering["rule1_maximum"]}. Therefore {clustering["quarantined_components"]:,} components were quarantined and {clustering["partial_merges_from_quarantine"]:,} were partially merged. The code and tests also verify that a size-12 component is accepted and a size-13 component is rejected in full.</div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([0.9, 1.4])
    with left:
        st.subheader("Component-size distribution")
        chart(data["cluster_sizes"], charts.cluster_distribution(), "cluster-distribution")
    with right:
        st.subheader("Recall by source pair")
        chart(data["source_pairs"][:8], charts.source_pair_recall(), "source-pair-recall")
        st.caption("Hover definitions are included for both recall measures. Frozen-test subgroups only; overall accuracy is intentionally omitted.")

elif page == "MCT decision lab":
    hero(
        "Put a candidate pair on trial",
        "Use the actual frozen logistic coefficients to inspect how evidence and conflicts combine. This educational tool does not modify production decisions.",
    )
    model = data["selected_model"]
    presets = {
        "Email and phone agreement": ["evidence:exact_email", "evidence:exact_phone"],
        "Verified email only": ["evidence:exact_verified_email"],
        "Name and city only": ["evidence:name_city"],
        "Household email and payment risk": ["evidence:exact_email", "evidence:exact_payment_token", "conflict:shared_email_payment_household_risk"],
        "Name and DOB with account conflict": ["evidence:name_date_of_birth", "conflict:account_reference_conflict"],
        "Eligible device only": ["evidence:exact_device_id"],
    }
    preset = st.selectbox("Prepared synthetic case", list(presets))
    base_events = [name for name in model["feature_names"] if " & " not in name]
    selected = st.multiselect(
        "Active model events",
        base_events,
        default=presets[preset],
        key=f"events-{preset}",
        help="Arbitrary combinations may be outside the observed training support.",
    )
    result = score_selected_model(model, selected)
    verdict_color = {"auto_merge": "#20B8A6", "human_review": "#F4A340", "leave_separate": "#8A98A8"}[result["decision"]]
    left, middle, right = st.columns([1, 1, 1.5])
    with left:
        st.metric("Model MCT", f"{result['score']:.6f}")
        with st.expander("Formula / definition"):
            st.markdown("`MCT = sigmoid(intercept + sum(active coefficients))`, rounded to six decimals before applying the fixed decision thresholds.")
    with middle:
        st.metric("Active events", f"{len(selected)}")
        with st.expander("Formula / definition"):
            st.markdown("Count of selected base evidence or conflict events. Interaction features activate automatically when both required base events are selected.")
    right.markdown(
        f'<div class="verdict" style="background:{verdict_color}">{result["decision_label"].upper()}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"`logit = {result['logit']:.6f}` → `sigmoid(logit) = {result['score']:.6f}`. Decisions use the published six-decimal score and fixed 0.62/0.88 boundaries."
    )
    if result["contributions"]:
        st.subheader("Largest active coefficient contributions")
        chart(result["contributions"][:10], charts.contribution_chart(), "contributions")
    else:
        st.info("No evidence event is active; the displayed score comes from the learned candidate-set intercept. A production record reaches this model only after blocking.")
    st.markdown(
        '<div class="callout warning"><b>Important.</b> This lab illustrates the selected model—not causal evidence strength. Rule 2 filtering and candidate construction happen before these features, and Rule 1 is enforced after the pair decision.</div>',
        unsafe_allow_html=True,
    )

else:
    hero(
        "What is fixed, learned and still uncertain?",
        "A defensible resolver separates assessment policy, our design choices, observed evidence and production limitations.",
    )
    left, right = st.columns(2)
    with left:
        st.subheader("Fixed by the assessment")
        st.markdown(
            """
            - MCT ≥ 0.88: auto-merge
            - 0.62 ≤ MCT < 0.88: human review
            - MCT < 0.62: leave separate
            - Rule 1: reject an entire transitive component above 12 records
            - Rule 2: a value occurring on more than 40 records has zero weight
            - Report precision and recall separately; do not report overall accuracy
            """
        )
    with right:
        st.subheader("Designed and defended here")
        st.markdown(
            """
            - Derived, non-destructive normalization
            - Rare-identifier and composite blocking
            - Person-disjoint labelled partitions
            - Heuristic, Fellegi-Sunter and logistic challengers
            - Precision-first model-selection gate
            - Observable automation and QA policy
            - Candidate simulation and unresolved-link sensitivity
            """
        )

    st.subheader("Development evidence, including dead ends")
    timeline = [
        ("Naive exact matcher", "813,387,806 candidate pairs and a 104,136-record poisoned component", "Rule 2 frequency suppression"),
        ("First blocker", "98.6614% recoverable blocking recall", "Nested social fields and iterative artifact cleanup"),
        ("Email + payment heuristic", "One household hard-negative auto-merge", "General 0.87 household-risk cap"),
        ("Pair-hash evaluation split", "33.6010% of endpoint people crossed partitions", "Person-component-disjoint split"),
        ("Fellegi-Sunter challenger", "One validation false auto-merge", "Interaction-aware logistic challenger"),
        ("Initial count range", "304,896–333,000 missed the 300,000-person fixture", "All-unresolved-link lower sensitivity"),
    ]
    for attempt, evidence, replacement in timeline:
        with st.expander(attempt):
            st.markdown(f"**Why it was dropped:** {evidence}  \n**Replacement:** {replacement}")

    st.subheader("Limitations to say out loud")
    st.markdown(
        """
        - The observed 100% auto-merge precision is finite synthetic-test evidence, not a production guarantee.
        - The 299,239 lower endpoint is a conservative sensitivity, not a confidence interval or merge plan.
        - The internal-QA rule is a business policy; the truth file has no independent QA label.
        - Real data can change identifier frequency, missingness, fraud patterns and model calibration.
        - Production deployment requires shadow testing, human review, audit logs, reversibility and drift monitoring.
        """
    )
    st.markdown(
        '<div class="callout"><b>Audit boundary.</b> This dashboard loads only committed aggregate JSON and CSV reports. It does not read raw source records, row-level classifications, person_map.csv, or hidden identifiers.</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")
st.caption("Kestrel Identity Resolution · Phase 14A · Read-only stakeholder view · Selected model: logistic MCT L2=0.001")
