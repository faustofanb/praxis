# MES PDA read-only overview behavior

## Page states

The page must distinguish:

- initial loading;
- filter-option loading;
- successful content;
- empty result;
- request failure with an explicit retry action.

Do not render an empty success card for a failed request. Retrying must reuse the currently confirmed filters.

## Filters

- Multi-select: at least one value remains selected; disable or reject empty confirmation.
- Single-select: include “全部” as a deliberate no-restriction value.
- Confirm: close the selector and query immediately.
- Cancel: preserve the last confirmed selection.
- First load: fetch required options, derive a deterministic default, then issue one data query.

## Request ownership

Use an abort signal, request token, or monotonically increasing sequence so only the newest request may update page data and error state. Disable duplicate submits only when that matches neighboring pages; never allow a slow older response to overwrite a newer filter result.

## Display

- Treat Snowflake IDs as strings end to end.
- Apply existing helpers for money, weight, and quantity; keep units visible and avoid implicit unit conversion.
- Preserve zero as data rather than replacing it with an empty placeholder.
- Keep prototype-specific field names and hierarchy in page-local configuration; the shared skeleton must not dictate business fields or colors.

## Route identity

The physical page path, Vue route block, `pages.json`, and `uni-pages.d.ts` must describe the same route. Run the repository's generator/check when present. All generated route changes belong to the bound worktree, even when the root repository already contains dirty generated route files.
