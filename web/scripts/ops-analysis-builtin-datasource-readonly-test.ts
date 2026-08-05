import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const readSource = (relativePath: string) =>
  readFileSync(new URL(relativePath, import.meta.url), "utf8");

const pageSource = readSource(
  "../src/app/ops-analysis/(pages)/settings/dataSource/page.tsx",
);
const modalSource = readSource(
  "../src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx",
);
const paramTableSource = readSource(
  "../src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx",
);
const fieldSchemaSource = readSource(
  "../src/app/ops-analysis/(pages)/settings/dataSource/fieldSchemaTable.tsx",
);

assert.match(
  pageSource,
  /row\.is_build_in[\s\S]{0,500}handleEdit\(["']view["'], row\)[\s\S]{0,200}t\(["']common\.view["']\)/,
  "内置数据源操作列应提供查看入口",
);
assert.match(
  pageSource,
  /<Tag[\s\S]{0,220}bordered=\{false\}[\s\S]{0,350}--color-fill-2[\s\S]{0,180}--color-text-3/,
  "内置标识应使用无描边、低对比度的主题语义样式",
);
assert.match(
  modalSource,
  /const readOnly = mode === "view";/,
  "查看模式应有明确的只读状态",
);
assert.match(
  modalSource,
  /<Form[\s\S]{0,180}disabled=\{readOnly\}/,
  "查看模式应通过 Ant Design Form 禁用表单控件",
);
assert.match(
  modalSource,
  /<ParamTable[\s\S]{0,180}readOnly=\{readOnly\}/,
  "参数表应接收只读状态",
);
assert.match(
  modalSource,
  /<FieldSchemaTable[\s\S]{0,180}readOnly=\{readOnly\}/,
  "字段定义表应接收只读状态",
);
assert.match(
  paramTableSource,
  /readOnly \? null : \(/,
  "只读参数表不应显示增删操作",
);
assert.match(
  fieldSchemaSource,
  /rowDraggable=\{!readOnly\}/,
  "只读字段定义表不应允许拖拽排序",
);

console.log("ops analysis built-in datasource readonly tests passed");
