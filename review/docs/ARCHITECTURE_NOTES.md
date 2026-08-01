# Architecture Notes
The repository-free engine runs immediately after snapshot acquisition at the DecisionPipeline boundary. It returns one immutable instance stored on DecisionContext and PipelineResults. Existing engines and recommendation mutation remain unchanged. `preview()` is an application-facing informational projection; no Streamlit layout was changed.
