// Pure, framework-free helpers for the dashboard track table.
// Imported both by the browser (as an ES module) and by the Node test runner.

/**
 * Return true if every whitespace-separated word in `query` appears as a
 * case-insensitive substring of `haystack`. A blank query matches everything.
 * The haystack is normalized (coerced to string and lowercased) internally.
 */
export function matchesQuery(haystack, query) {
  const hay = String(haystack ?? '').toLowerCase();
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return words.every((w) => hay.includes(w));
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
