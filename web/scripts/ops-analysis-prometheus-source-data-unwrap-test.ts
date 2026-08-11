import assert from "node:assert/strict";
import { unwrapSourceDataResponse } from "../src/app/ops-analysis/utils/sourceDataResponse";

const arrayPayload = [{ name: "a", value: 1 }];
assert.deepEqual(unwrapSourceDataResponse(arrayPayload), {
  data: arrayPayload,
  warnings: [],
});

const multiSeriesMap = {
  a: [{ name: 1, value: "2" }],
};
assert.deepEqual(unwrapSourceDataResponse(multiSeriesMap), {
  data: multiSeriesMap,
  warnings: [],
});

const envelopeWithWarnings = {
  data: [{ series: "cpu", name: "t", value: 1 }],
  warnings: ["x"],
};
assert.deepEqual(unwrapSourceDataResponse(envelopeWithWarnings), {
  data: envelopeWithWarnings.data,
  warnings: ["x"],
});

const envelopeWithEmptyWarnings = {
  data: [{ series: "cpu", name: "t", value: 1 }],
  warnings: [],
};
assert.deepEqual(unwrapSourceDataResponse(envelopeWithEmptyWarnings), {
  data: envelopeWithEmptyWarnings.data,
  warnings: [],
});

const dataOnlyPayload = {
  data: { series_a: [{ name: "t", value: 1 }] },
};
assert.deepEqual(unwrapSourceDataResponse(dataOnlyPayload), {
  data: dataOnlyPayload,
  warnings: [],
});

console.log("ops analysis prometheus source data unwrap tests passed");
