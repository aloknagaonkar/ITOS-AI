# Sprint 7 Summary

MarketRegimeEngine, SmartMoneyIndexEngine, MarketEnergyEngine, and EarlyWarningEngine now accept `DecisionContext` as their preferred input. Each retains a private legacy adapter and a single business-logic path. Dashboard execution reuses its one `MarketSnapshot` and one `DecisionContext`; result registration makes upstream dependencies available to later engines without placing runtime state in the snapshot.

Compatibility mapping input remains supported. Optional malformed values normalize to neutral inputs, and a blocked or incomplete recommendation cannot produce an actionable early-warning vote.
