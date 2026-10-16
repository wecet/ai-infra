import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createServer } from 'vite';

test('workspace components render without undefined state or missing references', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  const project = { id: 'project', name: 'Inspection', annotation_type: 'object_detection', permission: 'owner', classes: [{ id: 1, name: 'Bolt' }] };
  const previous = globalThis.window;
  globalThis.window = { sessionStorage: { getItem: () => null } };
  try {
    for (const name of ['Editor', 'Training', 'ModelEvaluation', 'Lineage', 'Project', 'Readiness', 'AnnotationImport', 'DatasetExplorer', 'ModelReviewQueue', 'RunComparison', 'Activity']) {
      const { default: Component } = await server.ssrLoadModule(`/src/components/${name}.jsx`);
      const props = { project, image: { id: 'image', width: 100, height: 80 }, model: { id: 'model', version_id: 'version' }, images: [], models: [], onSaved() {}, onLock() {}, onRefresh() {}, onUpdated() {}, onDeleted() {} };
      assert.ok(renderToString(React.createElement(Component, props)).length > 0, name);
    }
  } finally { globalThis.window = previous; await server.close(); }
});
