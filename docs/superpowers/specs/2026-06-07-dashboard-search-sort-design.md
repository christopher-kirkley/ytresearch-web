# Dashboard Search & Sort — Design

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Goal

Let a user quickly find and order tracks on the dashboard:

- **Search:** filter the track list by a keyword matched across title, artist,
  country, genre, and language/ethnic group.
- **Sort:** click any meaningful column header to sort ascending/descending.

## Scope & constraints

- Target archive size is small (< ~500 tracks per user), so all rows already
  render on one page. Filtering and sorting happen **entirely client-side** in
  the browser — no new routes, no SQL, no changes to `db.py` or `tasks.py`.
- The server continues to send all rows via the existing `dashboard` route and
  `db.get_tracks_for_user`. No pagination.
- Graceful degradation: with JavaScript disabled, the full unfiltered table
  still renders (current behavior preserved).

## Architecture

A frontend-only enhancement of the server-rendered table in
`src/ytresearch_web/templates/dashboard.html`.

1. **Add a Language column.** The table gains a visible "Language" column
   (between Country and Genre), sourced from `language_ethnic_group` (already
   returned by `get_tracks_for_user`). Columns become:
   `Title · Artist · Country · Language · Genre · Summary · Status · Added`.

2. **Data attributes as source of truth.** Each `<tr>` carries `data-*`
   attributes with the full, normalized values used for filter/sort, so search
   stays accurate even though some cells are truncated for display:
   - `data-title`, `data-artist`, `data-country`, `data-language`,
     `data-genre` — lowercased text (search + text sort)
   - `data-status` — status string (text sort)
   - `data-added` — ISO date string `YYYY-MM-DD` (reliable date sort)

3. **A search input + result count** above the table.

4. **Clickable column headers** for sorting.

5. **Vanilla JS**, matching the existing inline-script style already in
   `dashboard.html`. Filter predicate and sort comparator are factored into
   small pure functions so they can be unit-tested without a browser.

## Search behavior

- Single text input labeled e.g. "Search tracks…", placed above the table.
- Matching is **case-insensitive substring** of the query against any of:
  title, artist, country, language, genre.
- **Multi-word = AND:** the query is split on whitespace; a row matches only if
  every word is found in at least one of the searched fields (a word may match
  different fields).
- Debounced (~150 ms) on input for smoothness.
- A live "**N of M tracks**" count reflects current matches.
- When zero rows match, show an inline empty-state message
  ("No tracks match your search.").
- Clearing the input restores all rows.
- Summaries are intentionally **not** searched, to keep matches precise.

## Sort behavior

- Sortable columns: **Title, Artist, Country, Language, Genre, Status, Added.**
- Clicking a header sorts by that column; clicking again toggles asc ↔ desc.
- The active column shows a direction indicator (▲ / ▼).
- Text columns sort with `localeCompare` (correct ordering for accented and
  non-English text — relevant to this catalogue). Empty values sort last.
- **Added** sorts by the `data-added` ISO date attribute, not display text.
- **Default sort stays Added-descending** (newest first), matching current
  server order.
- Sorting reorders only the **currently visible** (post-filter) rows, so search
  and sort compose: search narrows, sort orders the result.

## Data flow

```
dashboard route (unchanged)
  -> db.get_tracks_for_user (unchanged)
  -> dashboard.html renders all rows + data-* attributes
  -> [browser] JS reads data-* attributes
       search input  -> filter predicate -> show/hide rows + update count
       header click  -> comparator       -> reorder visible rows
```

## Error handling / edge cases

- Empty/whitespace-only query → all rows shown.
- Rows with missing fields (null artist, etc.) → empty string; never throw;
  sort empties last.
- No tracks at all → existing "No tracks yet" message (unchanged).
- JS disabled → full table renders, no search/sort controls active.

## Testing

- Extract filter predicate and comparator into a tiny pure-JS module
  (e.g. `static/js/track-table.js`) and cover with a lightweight unit test:
  - substring match (case-insensitive)
  - multi-word AND across different fields
  - date sort order (asc/desc) via ISO attribute
  - text sort with empties pushed last
- Python test suite is untouched and must still pass.

## Out of scope (YAGNI)

- Server-side search / SQL queries / full-text indexing.
- Pagination.
- Searching summary text.
- Saved searches, URL-persisted query state, filter chips.

These become relevant only if per-user track counts grow well beyond ~500.
