# Known Issues

## Unresolved Test Issues
`python -m pytest -q` stops during collection because `pandas` is unavailable. There are no observed assertion failures because tests cannot execute.

## Environment Limitations
The Python 3.14.4 environment does not contain the dependencies from `requirements.txt`. Package installation is blocked by a package-index tunnel returning HTTP 403.

## Dependency Limitations
`pandas` and, transitively for the engine suite, `numpy` must be installed before the merge-gate test can run. CI or a provisioned development environment should execute the exact validation commands.

## Compatibility Adapters
`DecisionContext.from_legacy` and mapping-style `get` access on the typed contracts are intentionally temporary migration aids.

## Follow-up Work
Run the full suite in the dependency-provisioned CI environment and confirm zero collection errors and zero failures.

## Deferred Improvements
Migration of other engine interfaces and eventual removal of compatibility accessors are deferred to later sprints.
