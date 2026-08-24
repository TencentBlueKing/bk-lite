import assert from "node:assert/strict";
import { parseSourceDataResponse } from "../src/app/ops-analysis/utils/sourceDataResponse";

const arrayPayload = [{ name: "a", value: 1 }];
assert.deepEqual(parseSourceDataResponse({ data: arrayPayload, warnings: [] }), {
  data: arrayPayload,
  warnings: [],
});

const multiSeriesMap = {
  a: [{ name: 1, value: "2" }],
};
assert.deepEqual(parseSourceDataResponse({ data: multiSeriesMap, warnings: [] }), {
  data: multiSeriesMap,
  warnings: [],
});

const envelopeWithWarnings = {
  data: [{ series: "cpu", name: "t", value: 1 }],
  warnings: ["x"],
};
assert.deepEqual(parseSourceDataResponse(envelopeWithWarnings), {
  data: envelopeWithWarnings.data,
  warnings: ["x"],
});

const envelopeWithEmptyWarnings = {
  data: [{ series: "cpu", name: "t", value: 1 }],
  warnings: [],
};
assert.deepEqual(parseSourceDataResponse(envelopeWithEmptyWarnings), {
  data: envelopeWithEmptyWarnings.data,
  warnings: [],
});

const dataOnlyPayload = {
  data: { series_a: [{ name: "t", value: 1 }] },
};
assert.throws(() => parseSourceDataResponse(dataOnlyPayload), /统一取数响应格式无效/);

console.log("ops analysis source data transport envelope tests passed");
