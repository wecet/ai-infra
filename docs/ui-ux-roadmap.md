# UI/UX direction

Reviewed 12 October 2026. This document distinguishes improvements now implemented in source from proposals.

## Implemented foundation

AI Studio has task-aware Vision project creation, light/dark themes, grouped metric colours, readable annotations, field help, and error dialogs. Training now uses compact job cards with phase, elapsed time, heartbeat, latest metric, expandable persisted logs, and outcome-specific actions. Saved models open an evaluation dialog for their recorded held-out partition; untracked legacy models explain why verified evaluation is unavailable.

## Proposed next improvements

| Area | User problem | Proposed change | Acceptance check |
| --- | --- | --- | --- |
| Project overview | Users do not know the next required step | A task-aware prepare → publish → train → evaluate checklist | Anomaly projects never request labels; unmet requirements link to the relevant action |
| Imports | A failed batch is difficult to diagnose | Preview sample validity and show per-file progress, rejection reasons and retry | Successfully imported files are not uploaded again on retry |
| Training config | Generic fields can be irrelevant to a model | Schema-defined basic/advanced groups, applicability and presets | Unsupported options are absent; defaults and validated values are explicit |
| Dataset splits | Percentages conceal tiny or leaky partitions | Show actual counts, group constraints and sample previews | A user can identify an empty partition or duplicate leakage before publishing |
| Run comparison | Metrics across different datasets are misleading | Side-by-side comparison tied to one evaluation version and metric policy | Incomparable versions/tasks are explained instead of ranked |
| Model evaluation | Users need to find individual mistakes quickly | Search/filter predictions, confidence controls, confusion matrices and larger paginated example sets | Threshold changes are labelled exploratory and do not overwrite the saved evaluation |
| Lineage | Many runs make connections difficult to follow | Search, filters, collapse stages and selected-node details | Selected source/destination relationships remain clear in both themes |
| Feedback | Background work can look stalled | Phase-specific empty/loading states and an explicit last-contact indicator | A stale heartbeat says delayed/reconnecting, not automatically failed |

## Interaction and accessibility standards

- Keep actions compact and distinguish primary work from secondary external links.
- Use semantic colour groups consistent with the slate/coral brand; status must also have readable text.
- Preserve form values after validation errors and configuration cloning. Refreshing a page restores server-owned work, not a second submission.
- Native modal dialogs must trap focus, support Escape, restore focus, and have labelled headings.
- Expandable logs should have a bounded height, selectable text, timestamps and no forced page scrolling.
- Test keyboard navigation, zoom, narrow viewports, long names and both themes. Hover explanations must also be available on focus.
- Show which examples are ground-truth failures and which are unverified anomaly flags.

## Review scenarios

Verify empty, queued, training, validating, reconnecting, succeeded and failed jobs. Close the page during a run, reopen it, and confirm identity, elapsed time, logs and metrics. Open a legacy model, a model with no test samples, and an evaluated model. Confirm that model and evaluation errors remain recoverable without losing the training configuration.
