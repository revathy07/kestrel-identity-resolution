# Phase 13 customer-count and risk summary

## Recommended business statement

Kestrel has an estimated **315,177 human customers** under the candidate-resolvable scenario. A defensible range is **304,896 to 333,000**. The lower end includes an explicit zero-evidence sensitivity; the upper end assumes no uncertain candidate link resolves after high-confidence traffic exclusions.

This is an aggregate estimate, not permission to merge records below MCT 0.88. The operational identity table remains at 342,900 and keeps review/separate records distinct.

## Count bridge

- Source records: **420,000**
- Selected operational identities: **342,900**
- Observable automation clusters excluded: **8,400**
- Observable internal-QA clusters excluded: **1,500**
- Marketing-safe upper after exclusions: **333,000**
- Review-only median scenario: **319,679**
- All-candidate median scenario: **315,177**
- Candidate statistical interval: **315,001–315,357**
- Zero-evidence lower sensitivity: **304,896**

## Marketing versus Finance

Marketing's 400,000 is closest to an account/record count and is 84,823 above the recommended estimate. Finance's 300,000 is 15,177 below it. Marketing is counting duplicated system identities; Finance is directionally closer to people, but the evidence supports a range rather than an exact production total.

## Review workload

The queue contains **20,560 physical pairs** representing **15,247 unique operational-cluster pairs**. At two minutes each this is **685.3 analyst hours (85.7 eight-hour days)**; at five minutes it is **1713.3 hours (214.2 days)**. These are staffing scenarios, not measured handling times.

## False-merge consequence

A wrong merge can expose another person's orders, tickets, subscription relationship or address and can become a reportable privacy breach. The dataset provides no defensible currency cost, so none is invented. Rule 1 bounds an accepted automatic component at 12 source records, but a two-person merge is still unacceptable; monitoring, reversal tooling, incident investigation time, notification cost and regulatory/legal cost must be supplied before monetary expected loss can be calculated.

## Method and limitations

- Automation uses a discovered recent timestamp burst plus source-specific observable behaviour; no bot flag, hidden entity type, generator anchor or ID range is used.
- QA uses explicit test-domain/name policy and excludes only wholly flagged clusters.
- Frozen-test score-bin match rates drive 500 deterministic simulations with Jeffreys uncertainty.
- Candidate edges are collapsed to unique operational-cluster pairs, sampled, unioned transitively and checked against Rule 1.
- Simulations estimate aggregate people; they never rewrite operational clusters or accept below-threshold links.
- The lower zero-evidence sensitivity is deliberately conservative and may overstate the possible reduction because canonical links can overlap.
- Real production behaviour may differ from the synthetic fixture; ongoing labelled review and false-merge monitoring are required.
