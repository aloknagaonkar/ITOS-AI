# Known Issues

## Merge-gate Blocker
`python -m pytest -q` was invoked but stops during collection because `pandas` and
`numpy` are unavailable. Five collection errors occur and no tests execute, so the
required pytest merge gate is not satisfied in this container.

## Environment Limitations
The Python 3.14.4 environment lacks project dependencies. Both pip installation
and an apt repository attempt were blocked by the environment's HTTP 403 proxy.
A dependency-provisioned CI runner must execute the required pytest command.

## Compatibility Debt
Legacy mapping input through `RecommendationStabilityEngine._adapt_input` is
intentional temporary migration support. Most remaining engines still accept
mapping-shaped inputs and are deferred to later incremental sprints.
