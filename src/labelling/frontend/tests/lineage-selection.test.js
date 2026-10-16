import test from 'node:test';
import assert from 'node:assert/strict';
import { ancestors } from '../src/lineage-selection.js';
test('ancestry handles cycles and excludes unrelated nodes', () => {
  assert.deepEqual([...ancestors([{ from: 'a', to: 'b' }, { from: 'b', to: 'a' }, { from: 'c', to: 'd' }], 'b')].sort(), ['a', 'b']);
});
