<!-- Engineering: only fill the Bug fix section for a fix; feature/docs PRs may mark it N/A. Root-cause policy: AGENTS.md. -->

## Goal / change
<!-- What user-visible behavior or engineering outcome is intended? -->

## Bug fix — root cause and generalization (required for fixes)
- **Observed vs expected / reproduction:** 
- **Evidence and investigation:** 
- **Root cause and broken system invariant:** 
- **Affected flow and related scenarios:** 
- **Why this fixes the failure class (not just one example):** 
- **Alternatives / why no hardcoded special case:** 

## Validation
- **Regression reproduction (ideally fails on previous code):** 
- **Variants, boundary cases and negative cases:** 
- **Adjacent behavior, privacy, cost/performance and backwards compatibility:** 
- **Suites/CI actually run and results:** 
- **Production/live integration smoke:** Not yet performed / verified (choose and describe)

## Release and risk
- **What remains unverified:** 
- **Rollout, rollback or containment plan (if relevant):** 

> No "pass the test" fixes: investigate a failing assertion before modifying it.
> If only emergency containment was possible, label the PR "temporary mitigation"
> and track the permanent root-cause fix separately.
