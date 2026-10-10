import assert from "node:assert/strict";
import test from "node:test";
import { schemaDefaults, normalizeParams, resolveSchema, liveMetricsEnabled } from "../src/training-config.js";

const model = { config_schema: { $defs: { Augmentations: { type: "object", properties: { flip: { enum: ["vertical", "horizontal"] } } } }, properties: {
  dataset_path: { type: "string" }, epochs: { type: "integer", default: 2 }, learning_rate: { type: "number", default: 0.001 },
  augmentations: { $ref: "#/$defs/Augmentations", default: {} },
  callbacks: { type: "array", default: ["tensorboard", "gradcam"], items: { enum: ["tensorboard", "gradcam"] } },
} } };

test("blank fields use Pydantic defaults; structured inputs parse and empty callback lists stay empty", () => {
  assert.deepEqual(schemaDefaults(model), { epochs: 2, learning_rate: 0.001, augmentations: {}, callbacks: ["tensorboard", "gradcam"] });
  assert.deepEqual(normalizeParams({ epochs: "", learning_rate: "  ", augmentations: "", callbacks: [] }, model), {
    epochs: 2, learning_rate: 0.001, augmentations: {}, callbacks: [],
  });
  assert.deepEqual(normalizeParams({ augmentations: '{"blur":1,"flip":"vertical"}' }, model).augmentations, { blur: 1, flip: "vertical" });
  assert.equal(normalizeParams({ epochs: "3" }, model).epochs, 3);
  assert.equal(resolveSchema(model.config_schema.properties.augmentations, model.config_schema).type, "object");
  assert.throws(() => normalizeParams({ augmentations: "bad JSON" }, model), /valid JSON/);
  assert.throws(() => normalizeParams({ augmentations: "[]" }, model), /JSON object/);
  assert.throws(() => normalizeParams({ epochs: "1.5" }, model), /valid integer/);
});

test("metrics button hides when either callback is disabled", () => {
  assert.equal(liveMetricsEnabled({}, model), true);
  for (const callbacks of [[], ["tensorboard"], ["gradcam"]]) assert.equal(liveMetricsEnabled({ callbacks }, model), false);
  assert.equal(liveMetricsEnabled({}, { config_schema: {} }), false);
});
