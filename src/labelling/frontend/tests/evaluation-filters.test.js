import test from 'node:test';
import assert from 'node:assert/strict';
import { filterPredictions } from '../src/evaluation-filters.js';
test('filters retain ground truth class matches and combine confidence and search', () => {
  const rows = [{ source_path: 'Camera/a.png', predictions: [{ class_name: 'dog', score: .7 }], ground_truth: ['cat'], failed: true }];
  assert.equal(filterPredictions(rows, { query: 'CAMERA', category: 'cat', confidence: .6, failures: true }).length, 1);
  assert.equal(filterPredictions(rows, { confidence: .8 }).length, 0);
});
