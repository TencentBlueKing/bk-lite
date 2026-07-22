# Historical Superpowers change: 2026-06-30-monitor-strategy-aggregation-designer

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-30-monitor-strategy-aggregation-designer.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained Storybook prototype for the monitor strategy aggregation designer so product and engineering can review the new six-method grouping/window calculation experience.

**Architecture:** Add one contract test script that checks the prototype source for required product semantics, then add one isolated Storybook story with local mock data and no backend calls. The story renders configuration controls, calculation explanation, advanced query text, scenario preview, recommendations, and comparison states.

**Tech Stack:** Next.js Storybook, React 19, TypeScript, Ant Design 5, Node `tsx` script tests.

---

### Task 1: Story Contract Test

**Files:**
- Create: `web/scripts/monitor-strategy-aggregation-designer-story-test.ts`
- Modify: `web/package.json`

- [ ] **Step 1: Write the failing test**

Create `web/scripts/monitor-strategy-aggregation-designer-story-test.ts` with source checks for:

```ts
import fs from 'fs';
import path from 'path';

const storyPath = path.join(
  process.cwd(),
  'src/stories/monitor-strategy-aggregation-designer.stories.tsx'
);

const assert = (condition: unknown, message: string) => {
  if (!condition) {
    throw new Error(message);
  }
};

assert(fs.existsSync(storyPath), 'Monitor strategy aggregation designer story should exist');

const storySource = fs.readFileSync(storyPath, 'utf8');

[
  "title: 'Monitor/StrategyAggregationDesigner'",
  'AggregationDesignerFrame',
  'DefaultNumericMetric',
  'InterfaceStatusLast',
  'DeltaCounterSum',
  'MethodComparison',
  'Average',
  'Maximum',
  'Minimum',
  'Accumulated',
  'Valid count',
  'Latest value',
  'avg_over_time((avg(metric) by (group_by))[5m:1m])',
  'count(last_over_time(metric[5m])) by (group_by)',
  'any(last_over_time(metric[5m])) by (group_by)',
  'Aggregation period is the observation window',
  'SUM is usually not appropriate for gauge metrics',
].forEach((expected) => {
  assert(storySource.includes(expected), `Story should include ${expected}`);
});

[
  'AVG_OVER_TIME',
  'MAX_OVER_TIME',
  'MIN_OVER_TIME',
  'SUM_OVER_TIME',
].forEach((legacyMethod) => {
  assert(!storySource.includes(`label: '${legacyMethod}'`), `${legacyMethod} should not be a visible method label`);
});

console.log('monitor strategy aggregation designer story contract OK');
```

Add a package script:

```json
"test:monitor-strategy-aggregation-designer": "pnpm exec tsx scripts/monitor-strategy-aggregation-designer-story-test.ts"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web && pnpm test:monitor-strategy-aggregation-designer
```

Expected: FAIL because the story file does not exist.

- [ ] **Step 3: Commit only after green**

Do not commit in this task until Task 2 is green.

### Task 2: Storybook Prototype

**Files:**
- Create: `web/src/stories/monitor-strategy-aggregation-designer.stories.tsx`
- Test: `web/scripts/monitor-strategy-aggregation-designer-story-test.ts`

- [ ] **Step 1: Implement the story**

Create a self-contained story that:

- Exports `AggregationDesignerFrame`.
- Uses six methods: `AVG`, `MAX`, `MIN`, `SUM`, `COUNT`, `LAST`.
- Provides mock metrics for disk usage, interface status, request increment, and interface inventory.
- Shows configuration controls in the left column.
- Shows step-by-step calculation explanation and advanced query text in the right column.
- Shows scenario preview and recommendations below.
- Exports stories `DefaultNumericMetric`, `InterfaceStatusLast`, `DeltaCounterSum`, and `MethodComparison`.

- [ ] **Step 2: Run contract test**

Run:

```bash
cd web && pnpm test:monitor-strategy-aggregation-designer
```

Expected: PASS and print `monitor strategy aggregation designer story contract OK`.

- [ ] **Step 3: Run TypeScript check for changed files**

Run:

```bash
cd web && pnpm exec tsc --noEmit --pretty false --jsx react-jsx --moduleResolution bundler --module esnext --target es2022 --lib dom,dom.iterable,es2022 --allowSyntheticDefaultImports --esModuleInterop --skipLibCheck scripts/monitor-strategy-aggregation-designer-story-test.ts
```

Expected: PASS for the script. If full app type-check is affordable, run `pnpm type-check` afterward.

- [ ] **Step 4: Commit**

Run:

```bash
git add web/package.json web/scripts/monitor-strategy-aggregation-designer-story-test.ts web/src/stories/monitor-strategy-aggregation-designer.stories.tsx docs/superpowers/plans/2026-06-30-monitor-strategy-aggregation-designer.md
git commit -m "feat(monitor): prototype aggregation method designer"
```

### Task 3: Storybook Runtime Review

**Files:**
- Verify: `web/src/stories/monitor-strategy-aggregation-designer.stories.tsx`

- [ ] **Step 1: Start Storybook**

Run:

```bash
cd web && pnpm storybook
```

Expected: Storybook serves on `http://localhost:6006`.

- [ ] **Step 2: Open the story**

Open:

```text
http://localhost:6006/?path=/story/monitor-strategyaggregationdesigner--default-numeric-metric
```

Expected: The prototype renders without a blank page.

- [ ] **Step 3: Visual checks**

Verify:

- Six method options are visible.
- Legacy four `*_OVER_TIME` numeric methods are not visible.
- The explanation changes when method or metric changes.
- The advanced query shows explicit `5m:1m` resolution for numeric trend methods.
- The `LAST` state story explains interface up/down output.

---

## Self-Review

- Spec coverage: The plan covers the Storybook prototype, six methods, method explanations, explicit subquery resolution in advanced examples, recommendations, and source-level tests.
- Placeholder scan: No task relies on `TODO`, `TBD`, or undefined follow-up work.
- Scope check: This plan intentionally excludes backend query changes and data migration, matching the approved prototype-first scope.
