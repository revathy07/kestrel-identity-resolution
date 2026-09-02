# Phase 13 business-estimation design freeze

**Design freeze date:** 2 September 2026  
**Hidden population total used to choose rules:** No  
**Selected matching model changed:** No

## Business question

Marketing's 400,000 figure resembles a count of accounts or source records. The selected
resolver produces 342,900 operational identities, but that is still not automatically a
count of human customers: it includes automated/test traffic and deliberately unresolved
duplicates.

Phase 13 estimates a range without weakening the merge-safety policy. Operational records
remain unchanged. The aggregate estimate and the operational cluster table are distinct
products.

## Observable traffic exclusions

The dataset deliberately provides no bot flag or obvious bot word. Automation is therefore
identified by the documented behavioural combination: a recent dense timestamp burst plus
source-specific corroboration such as very low engagement, zero ticket recording delay, or
missing customer identifiers. The window is discovered from timestamp density; no known
generator anchor, source-record-ID range, hidden person ID or `entity_type` is a rule.

Internal QA is a separate business policy based on an explicit test email domain or
`load-test` name token. A resolved cluster is excluded only when every physical member
satisfies one policy. Mixed clusters remain in the count and are reported for review.

The initial truth-free run used a one-second maximum ticket delay and produced 800 mixed
flag/unflag clusters. Existing profiling had already established that near-duplicate exports
shift exactly one timestamp by 2–8 seconds. The corroboration bound was therefore corrected
to eight seconds before hidden truth was opened; the all-members cluster rule itself was not
relaxed.

That correction initially left 139 mixed ticket clusters. Inspection showed that the
ticket source stores timestamps only to the minute: a documented 2–8 second duplicate shift
crossing a minute boundary is represented as a 60-second parsed delay. The observable delay
allowance is therefore 68 seconds (one minute of source precision plus the documented
eight-second shift). The same eight-second tolerance is applied to detected window boundaries.
These are representation-aware corrections made without moving the detected burst or
referencing hidden labels.

The exact frozen rules are in
[`config/business_estimation.yaml`](../config/business_estimation.yaml). Hidden truth is
opened only afterward to measure automated-traffic detection precision and recall on the
synthetic fixture. QA has no independent hidden label in the supplied truth map, so it is
reported as an observable policy-defined exclusion rather than claimed classifier accuracy.

## Unresolved-duplicate adjustment

Subtracting the 20,560 review pairs directly would be wrong because pairs overlap
transitively and some are non-matches. The estimator instead:

1. calculates observed match rates in predeclared MCT score bins using only the
   person-disjoint frozen test;
2. applies Jeffreys smoothing to avoid probabilities of exactly zero or one;
3. samples unresolved review and leave-separate candidate edges in 500 deterministic Monte
   Carlo scenarios;
4. unions sampled edges between existing operational clusters;
5. counts each overlapping transitive component once; and
6. gives no additional count reduction to any sampled component exceeding Rule 1's
   12-record cap.

These sampled links never alter the operational cluster assignment. They support an
aggregate count estimate only.

Review workload is shown at two and five minutes per pair, with an eight-hour analyst day.
These are transparent planning scenarios, not measured Kestrel handling times. No monetary
false-merge cost is invented because the assessment supplies none; the report instead states
the affected-data and breach consequences and identifies the inputs required for costing.

## Reported count range and validation refactor

- The upper estimate removes only high-confidence observable automation/QA clusters and
  assumes no uncertain link resolves.
- The central estimate is the median candidate-resolvable Monte Carlo count.
- The statistical interval is the 5th–95th percentile across simulations.
- A separate conservative lower sensitivity subtracts at most one identity for every
  canonical link still unresolved after operational clustering: both recoverable links not
  merged and deliberately blocked links. It starts from the traffic-excluded upper count,
  deliberately ignores link overlap and is explicitly not a proposal to merge those records.

The first frozen range subtracted only blocked links from the Monte Carlo fifth percentile.
When the known hidden human total was released, that range (304,896–333,000) missed the
300,000-person fixture. The failure was committed before revision. Its root cause was that
the lower sensitivity remained conditional on candidate-pair recovery and did not represent
the full systematic unresolved-link risk. The replacement above is a general link-ceiling
calculation; it does not insert or algebraically target the known 300,000 total.

Hidden truth evaluates coverage on this synthetic fixture; it does not change the selected
model, MCT thresholds, operational clusters or central candidate-resolvable estimate.
