# Phase 7 capped-clustering report

## Outcome

- Physical source records: **420,000**
- MCT auto-merge edges consumed: **99,272**
- Proposed connected components: **342,900**
- Accepted merged components: **57,403**
- Accepted singleton components: **285,497**
- Components rejected by Rule 1: **0**
- Records quarantined: **0**
- Final resolved identity records: **342,900**

## Rule 1

Components containing up to and including 12 physical source records are accepted. Any component containing 13 or more is rejected in full and quarantined. Its members receive no final cluster ID, none of its edges are partially retained, and the MCT threshold is not changed.

## Component-size distribution

| Size | Status | Components | Records |
|---|---|---|---|
| 1 | accepted_singleton | 285,497 | 285,497 |
| 2 | accepted_merged | 39,181 | 78,362 |
| 3 | accepted_merged | 17,547 | 52,641 |
| 4 | accepted_merged | 175 | 700 |
| 5 | accepted_merged | 200 | 1,000 |
| 6 | accepted_merged | 300 | 1,800 |

## Largest proposed component

The largest proposed component contains **6** source records and **15** auto-merge edges. Its source composition is `{"app_users": 1, "social_logins": 4, "ticketing": 1}` and its status is `accepted_merged`.

## Quarantine

No component exceeded the 12-record cap; the quarantine is empty.

## Isolation and handoff

Production clustering reads only normalized record identity, Phase 6 scores and configuration. Hidden labels are opened later by the separate cluster evaluator. Human-review edges are not merged. Final business counts still need interpretation of the review queue and automated traffic.
