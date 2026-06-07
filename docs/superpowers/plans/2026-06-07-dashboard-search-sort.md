# Dashboard Search & Sort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-side keyword search and click-to-sort to the dashboard track table, plus a visible Language column.

**Architecture:** Pure frontend enhancement of the existing server-rendered table. Search/sort logic lives in a small, framework-free ES module (`static/js/track-table.js`) that is unit-tested with Node's built-in test runner and imported by an inline module script in `dashboard.html`. No routes, SQL, or Python changes. Each `<tr>` carries `data-*` attributes as the source of truth for filtering and sorting; the server keeps sending all rows.

**Tech Stack:** Flask/Jinja templates, vanilla ES modules, Node 24 `node:test` (no npm dependencies).

---

## File Structure

- **Create:** `package.json` — sets `"type": "module"` so Node treats `.js` as ESM for testing.
- **Create:** `src/ytresearch_web/static/js/track-table.js` — pure helpers: `matchesQuery`, `makeComparator`.
- **Create:** `tests/js/track-table.test.js` — Node unit tests for the helpers.
- **Modify:** `src/ytresearch_web/templates/dashboard.html` — Language column, `data-*` attributes, search input + count, sortable headers, inline module glue.
- **Modify:** `.gitignore` — ignore `node_modules/`.
- **Modify:** `README.md` — document the JS test command.

The Flask default static folder is `static/` inside the package (`src/ytresearch_web/static`), served at `/static`. No `app.py` change is needed: `Flask(__name__, template_folder="templates")` keeps the default `static_folder`. The CSP header (`script-src 'self' 'unsafe-inline'`) already permits an inline module that imports a same-origin file.

---

## Task 1: Pure search/sort logic module (TDD)

**Files:**
- Create: `package.json`
- Create: `tests/js/track-table.test.js`
- Create: `src/ytresearch_web/static/js/track-table.js`
- Modify: `.gitignore`

- [ ] **Step 1: Create `package.json` so Node treats `.js` files as ES modules**

```json
{
  "name": "ytresearch-web",
  "private": true,
  "type": "module"
}
```

- [ ] **Step 2: Add `node_modules/` to `.gitignore`**

Append this block to `.gitignore`:

```
# Node
node_modules/
```

- [ ] **Step 3: Write the failing test**

Create `tests/js/track-table.test.js`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matchesQuery, makeComparator } from '../../src/ytresearch_web/static/js/track-table.js';

test('empty or blank query matches everything', () => {
  assert.equal(matchesQuery('anything here', ''), true);
  assert.equal(matchesQuery('anything here', '   '), true);
});

test('single word matches case-insensitively', () => {
  assert.equal(matchesQuery('zambian pop bemba', 'BEMBA'), true);
  assert.equal(matchesQuery('zambian pop bemba', 'reggae'), false);
});

test('multi-word query is AND across the whole haystack', () => {
  assert.equal(matchesQuery('zambia bemba pop', 'zambia pop'), true);
  assert.equal(matchesQuery('zambia bemba pop', 'zambia reggae'), false);
});

test('text comparator sorts ascending and descending', () => {
  const asc = ['banana', 'apple', 'cherry'].sort(makeComparator('text', 'asc'));
  assert.deepEqual(asc, ['apple', 'banana', 'cherry']);
  const desc = ['banana', 'apple', 'cherry'].sort(makeComparator('text', 'desc'));
  assert.deepEqual(desc, ['cherry', 'banana', 'apple']);
});

test('empty values sort last in both directions', () => {
  const asc = ['', 'apple', ''].sort(makeComparator('text', 'asc'));
  assert.deepEqual(asc, ['apple', '', '']);
  const desc = ['', 'apple', 'banana'].sort(makeComparator('text', 'desc'));
  assert.deepEqual(desc, ['banana', 'apple', '']);
});

test('date comparator orders ISO date strings', () => {
  const asc = ['2026-01-05', '2025-12-31', '2026-03-01'].sort(makeComparator('date', 'asc'));
  assert.deepEqual(asc, ['2025-12-31', '2026-01-05', '2026-03-01']);
  const desc = ['2026-01-05', '2025-12-31', '2026-03-01'].sort(makeComparator('date', 'desc'));
  assert.deepEqual(desc, ['2026-03-01', '2026-01-05', '2025-12-31']);
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `node --test tests/js/track-table.test.js`
Expected: FAIL — cannot find module `track-table.js` (file does not exist yet).

- [ ] **Step 5: Implement the module**

Create `src/ytresearch_web/static/js/track-table.js`:

```js
// Pure, framework-free helpers for the dashboard track table.
// Imported both by the browser (as an ES module) and by the Node test runner.

/**
 * Return true if every whitespace-separated word in `query` appears as a
 * case-insensitive substring of `haystack`. A blank query matches everything.
 * `haystack` is expected to be already lowercased by the caller.
 */
export function matchesQuery(haystack, query) {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return words.every((w) => haystack.includes(w));
}

/**
 * Build a comparator for Array.prototype.sort.
 * `type` is 'text' or 'date'. `dir` is 'asc' or 'desc'.
 * Empty/null values always sort last, regardless of direction.
 */
export function makeComparator(type, dir) {
  return (a, b) => {
    const aEmpty = a === '' || a == null;
    const bEmpty = b === '' || b == null;
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    let cmp;
    if (type === 'date') {
      cmp = a < b ? -1 : a > b ? 1 : 0;
    } else {
      cmp = a.localeCompare(b);
    }
    return dir === 'desc' ? -cmp : cmp;
  };
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `node --test tests/js/track-table.test.js`
Expected: PASS — all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add package.json .gitignore tests/js/track-table.test.js src/ytresearch_web/static/js/track-table.js
git commit -m "Add tested search/sort helpers for dashboard table"
```

---

## Task 2: Wire search & sort into the dashboard template

**Files:**
- Modify: `src/ytresearch_web/templates/dashboard.html`

This task has no automated test (it is DOM glue, consistent with the existing inline-script approach in this file). Verification is manual via the running app in Step 6.

- [ ] **Step 1: Replace the table header row to add the Language column and make headers sortable**

In `src/ytresearch_web/templates/dashboard.html`, replace the existing `<thead>...</thead>` block:

```html
    <thead>
        <tr>
            <th>Title</th>
            <th>Artist</th>
            <th>Country</th>
            <th>Genre</th>
            <th>Summary</th>
            <th>Status</th>
            <th>Added</th>
        </tr>
    </thead>
```

with:

```html
    <thead>
        <tr>
            <th class="sortable" data-key="title" data-type="text">Title<span class="sort-ind"></span></th>
            <th class="sortable" data-key="artist" data-type="text">Artist<span class="sort-ind"></span></th>
            <th class="sortable" data-key="country" data-type="text">Country<span class="sort-ind"></span></th>
            <th class="sortable" data-key="language" data-type="text">Language<span class="sort-ind"></span></th>
            <th class="sortable" data-key="genre" data-type="text">Genre<span class="sort-ind"></span></th>
            <th>Summary</th>
            <th class="sortable" data-key="status" data-type="text">Status<span class="sort-ind"></span></th>
            <th class="sortable" data-key="added" data-type="date">Added<span class="sort-ind"></span></th>
        </tr>
    </thead>
```

- [ ] **Step 2: Replace the table body row markup to add `data-*` attributes and the Language cell**

Replace the existing `{% for t in tracks %} ... {% endfor %}` row block:

```html
        {% for t in tracks %}
        <tr id="row-{{ t.youtube_id }}">
            <td><a class="track-link" href="{{ url_for('track_detail', youtube_id=t.youtube_id) }}">{{ t.title or '(untitled)' }}</a></td>
            <td>{{ t.artist or '' }}</td>
            <td>{{ t.country or '' }}</td>
            <td>{{ t.genre or '' }}</td>
            <td>{{ (t.summary_short or '')[:80] }}{% if t.summary_short and t.summary_short|length > 80 %}...{% endif %}</td>
            <td><span class="status-badge status-{{ t.status }}">{{ t.status }}</span></td>
            <td>{{ t.created_at.strftime('%Y-%m-%d') if t.created_at else '' }}</td>
        </tr>
        {% endfor %}
```

with:

```html
        {% for t in tracks %}
        <tr id="row-{{ t.youtube_id }}"
            data-title="{{ (t.title or '')|lower }}"
            data-artist="{{ (t.artist or '')|lower }}"
            data-country="{{ (t.country or '')|lower }}"
            data-language="{{ (t.language_ethnic_group or '')|lower }}"
            data-genre="{{ (t.genre or '')|lower }}"
            data-status="{{ t.status or '' }}"
            data-added="{{ t.created_at.strftime('%Y-%m-%d') if t.created_at else '' }}">
            <td><a class="track-link" href="{{ url_for('track_detail', youtube_id=t.youtube_id) }}">{{ t.title or '(untitled)' }}</a></td>
            <td>{{ t.artist or '' }}</td>
            <td>{{ t.country or '' }}</td>
            <td>{{ t.language_ethnic_group or '' }}</td>
            <td>{{ t.genre or '' }}</td>
            <td>{{ (t.summary_short or '')[:80] }}{% if t.summary_short and t.summary_short|length > 80 %}...{% endif %}</td>
            <td><span class="status-badge status-{{ t.status }}">{{ t.status }}</span></td>
            <td>{{ t.created_at.strftime('%Y-%m-%d') if t.created_at else '' }}</td>
        </tr>
        {% endfor %}
```

- [ ] **Step 3: Add the search input + result count above the table**

Replace the line:

```html
<h2 style="margin-bottom: 1rem;">Tracks</h2>
{% if tracks %}
<table>
```

with:

```html
<h2 style="margin-bottom: 1rem;">Tracks</h2>
{% if tracks %}
<div class="form-row" style="align-items: center;">
    <input type="text" id="track-search" placeholder="Search title, artist, country, language, genre…">
    <span id="track-count" style="color: #666; white-space: nowrap;"></span>
</div>
<p id="search-empty" style="display: none; color: #666;">No tracks match your search.</p>
<table>
```

- [ ] **Step 4: Add header sort affordance styling**

Add these rules inside the existing `<style>` block (the one containing `@keyframes spin`), so it reads:

```html
<style>
@keyframes spin { to { transform: rotate(360deg); } }
th.sortable { cursor: pointer; user-select: none; }
th.sortable:hover { background: #16213e; }
.sort-ind { display: inline-block; width: 1em; }
</style>
```

- [ ] **Step 5: Add the inline module that wires search and sort**

Immediately after the closing `</script>` of the existing process-form script (the last line before `{% endblock %}`), add this new script block:

```html
<script type="module">
import { matchesQuery, makeComparator } from "{{ url_for('static', filename='js/track-table.js') }}";

const tbody = document.getElementById('tracks-body');
const searchInput = document.getElementById('track-search');
const countEl = document.getElementById('track-count');
const emptyEl = document.getElementById('search-empty');

// Only run if the table is present (it is hidden when there are no tracks).
if (tbody && searchInput) {
    const SEARCH_KEYS = ['title', 'artist', 'country', 'language', 'genre'];
    let sortState = { key: 'added', dir: 'desc' };

    const allRows = () => Array.from(tbody.querySelectorAll('tr'));
    const haystack = (row) => SEARCH_KEYS.map((k) => row.dataset[k] || '').join(' ');

    function applyFilter() {
        const q = searchInput.value;
        const rows = allRows();
        let visible = 0;
        for (const row of rows) {
            const show = matchesQuery(haystack(row), q);
            row.style.display = show ? '' : 'none';
            if (show) visible++;
        }
        countEl.textContent = `${visible} of ${rows.length} tracks`;
        emptyEl.style.display = visible === 0 ? 'block' : 'none';
    }

    function updateIndicators() {
        document.querySelectorAll('th.sortable').forEach((th) => {
            const ind = th.querySelector('.sort-ind');
            ind.textContent = th.dataset.key === sortState.key
                ? (sortState.dir === 'asc' ? ' ▲' : ' ▼')
                : '';
        });
    }

    function applySort() {
        const { key, dir } = sortState;
        const th = document.querySelector(`th.sortable[data-key="${key}"]`);
        const type = th ? th.dataset.type : 'text';
        const cmp = makeComparator(type, dir);
        const rows = allRows();
        rows.sort((ra, rb) => cmp(ra.dataset[key] || '', rb.dataset[key] || ''));
        for (const row of rows) tbody.appendChild(row); // reorder in place
        updateIndicators();
    }

    document.querySelectorAll('th.sortable').forEach((th) => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (sortState.key === key) {
                sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
            } else {
                sortState = { key, dir: 'asc' };
            }
            applySort();
        });
    });

    let debounce;
    searchInput.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(applyFilter, 150);
    });

    applySort();   // establish default newest-first order + indicator
    applyFilter(); // populate the "N of M tracks" count
}
</script>
```

- [ ] **Step 6: Manually verify in the browser**

Start the server (if not already running):

```bash
uv run flask --app ytresearch_web.app run --port 5001
```

Then verify the rendered page is well-formed without logging in (the markup is what matters):

```bash
curl -s http://127.0.0.1:5001/login | grep -c "Search title"   # expect 0 (login page, no table)
```

Log in at http://127.0.0.1:5001 (admin / admin from `.env`) and confirm by hand:
- A "Language" column appears between Country and Genre.
- Typing in the search box filters rows live; the "N of M tracks" count updates; clearing restores all rows; a no-match query shows "No tracks match your search."
- Clicking a column header sorts it; clicking again reverses; a ▲/▼ indicator marks the active column; "Added" defaults to newest-first on load.
- Search then sort compose (sorting keeps hidden rows hidden).

If there are no tracks yet, process one URL first so the table renders.

- [ ] **Step 7: Commit**

```bash
git add src/ytresearch_web/templates/dashboard.html
git commit -m "Add client-side search, sort, and Language column to dashboard"
```

---

## Task 3: Document the JS test command and verify both suites

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Tests section of `README.md`**

Replace the existing `## Tests` section:

```markdown
## Tests

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/ytresearch_test uv run pytest
```

Tests requiring a database skip automatically when `TEST_DATABASE_URL` is unset.
```

with:

```markdown
## Tests

Python (database tests skip automatically when `TEST_DATABASE_URL` is unset):

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/ytresearch_test uv run pytest
```

Frontend search/sort helpers (Node's built-in runner, no dependencies):

```bash
node --test tests/js/
```
```

- [ ] **Step 2: Run both test suites to confirm nothing regressed**

Run: `node --test tests/js/`
Expected: PASS — all helper tests pass.

Run: `uv run pytest -q`
Expected: PASS or all-skipped (when `TEST_DATABASE_URL` is unset) — no failures, no import errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document frontend test command"
```

---

## Self-Review Notes

- **Spec coverage:** client-side architecture (Task 2), search across title/artist/country/genre/language with case-insensitive multi-word AND (Task 1 `matchesQuery` + Task 2 `SEARCH_KEYS`), live count + empty state (Task 2 Steps 3, 5), all six columns sortable with asc/desc toggle + indicator and newest-first default (Task 2 Step 5), `localeCompare` text sort + ISO date sort + empties-last (Task 1 `makeComparator`), visible Language column (Task 2 Steps 1–2), data attributes for accurate search despite truncation (Task 2 Step 2), graceful degradation with JS off (full table still renders; the inline module is additive), unit tests for the pure logic (Task 1). All spec sections map to a task.
- **Out of scope confirmed absent:** no SQL, pagination, summary search, or persisted query state.
- **Type/name consistency:** `matchesQuery(haystack, query)` and `makeComparator(type, dir)` signatures match between Task 1's implementation, its tests, and Task 2's usage. `data-key` values (`title/artist/country/language/genre/status/added`) line up between headers (Step 1), row attributes (Step 2), and `SEARCH_KEYS`/`sortState` (Step 5). `data-type` is `text` everywhere except `added` which is `date`, matching `makeComparator`'s `type` argument.
