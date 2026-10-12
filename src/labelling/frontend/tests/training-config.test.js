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

test("workspace choices resolve their own enums without injecting demo options", () => {
  const schema = { $defs: {
    Callback: { type: "string", enum: ["early_stopping", "checkpoint"] },
    Flip: { type: "string", const: "horizontal" },
  }, properties: {
    callbacks: { type: "array", items: { $ref: "#/$defs/Callback" }, default: ["checkpoint"] },
    augmentations: { type: "object", properties: { flip: { $ref: "#/$defs/Flip" } }, default: {} },
  } };
  assert.deepEqual(resolveSchema(schema.properties.callbacks, schema).items.enum, ["early_stopping", "checkpoint"]);
  assert.deepEqual(resolveSchema(schema.properties.augmentations, schema).properties.flip.enum, ["horizontal"]);
  assert.deepEqual(schemaDefaults({ config_schema: schema }), { callbacks: ["checkpoint"], augmentations: {} });
  assert.equal(liveMetricsEnabled({}, { config_schema: schema }), false);
  assert.equal("callbacks" in schemaDefaults({ config_schema: { properties: {} } }), false);
});


test("TensorBoard links target one exact run on Time Series and retain the job's agent", async () => {
  const { dashboardUrl } = await import("../src/training-config.js");
  const job = { id: "id", run_name: "261010-test.project-v1", tensorboard_url: "http://agent:6006/", compute_target: { kind: "remote" } };
  const url = new URL(dashboardUrl(null, job));
  assert.equal(url.hash, "#timeseries");
  const filter = new RegExp(url.searchParams.get("runFilter"));
  assert.equal(filter.test("261010-test.project-v1/tensorboard"), true);
  assert.equal(filter.test("261010-testXproject-v1/tensorboard"), false);
  assert.equal(filter.test("261010-other-v1/tensorboard"), false);
  assert.equal(dashboardUrl(null, { ...job, tensorboard_url: "javascript:alert(1)" }), null);
});
