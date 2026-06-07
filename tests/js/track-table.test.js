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
