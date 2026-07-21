# TopN Runtime Control Header Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the TopN runtime dimension Segmented into the Dashboard Widget title row at the upper right while preserving one state source and an inline fallback outside Dashboard cards.

**Architecture:** Add a small context-backed DOM slot provider around each Dashboard Widget card. `WidgetWrapper`, which already owns the instance runtime value, portals a reusable Segmented component into that slot and tells `ComTopN` to suppress its inline copy. Containers without the slot keep the current inline rendering.

**Tech Stack:** React 18 context/portal, TypeScript, Ant Design Segmented, Tailwind utility classes, existing tsx contract script.

## Global Constraints

- The title stays left and truncates before the control moves or wraps.
- The Segmented stays at the upper right, does not wrap, and scrolls horizontally inside its bounded container when necessary.
- Loading, error, empty, and row states keep the header control visible.
- Runtime value remains owned by each `WidgetWrapper`; it is not persisted, lifted to Dashboard context, or duplicated.
- Historical TopN widgets without a valid control render no empty header slot content.
- Request parameters, cache signatures, ranking fields, sorting, progress bars, and `onReady` semantics do not change.
- Do not stage, commit, push, create a PR, reset, stash, or switch branches.

---

### Task 1: Dashboard title slot and TopN portal control

**Files:**
- Create: `web/src/app/ops-analysis/components/widgetHeaderRuntimeSlot.tsx`
- Create: `web/src/app/ops-analysis/components/widgets/runtimeParamSegmented.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comTopN.tsx`
- Modify: `web/scripts/ops-analysis-topn-runtime-param-test.ts`
- Modify: `web/src/app/ops-analysis/components/widgets/widgetShowcase.stories.tsx`

**Interfaces:**
- Produces: `WidgetHeaderRuntimeSlotProvider`, `useWidgetHeaderRuntimeSlot`, and `RuntimeParamSegmented`.
- Consumes: existing `RuntimeParamControl`, `RuntimeParamValue`, `getRuntimeParamSegmentedOptions`, and `hasRuntimeParamSegmentedValue`.
- `WidgetRenderer` adds `runtimeParamControlPlacement?: 'header' | 'inline'` only to the TopN conditional interaction props.

- [ ] **Step 1: Extend the contract script first**

Add assertions that require:

```ts
assert.match(dashboardCanvasSource, /WidgetHeaderRuntimeSlotProvider/);
assert.match(dashboardCanvasSource, /ref=\{runtimeSlotRef\}/);
assert.match(dashboardCanvasSource, /max-w-\[70%\]/);
assert.match(dashboardCanvasSource, /overflow-x-auto/);
assert.match(widgetDataRendererSource, /createPortal/);
assert.match(widgetDataRendererSource, /useWidgetHeaderRuntimeSlot/);
assert.match(widgetDataRendererSource, /runtimeParamControlPlacement/);
assert.match(topNSource, /runtimeParamControlPlacement !== 'header'/);
assert.doesNotMatch(topNSource, /<Segmented/);
```

Also read `runtimeParamSegmented.tsx` and assert it uses the existing option/validity helpers, `min-w-max`, and forwards the original value through `onChange`.

- [ ] **Step 2: Run the script and verify RED**

Run:

```powershell
cd web
pnpm test:ops-analysis-topn-runtime-param
```

Expected: FAIL because `widgetHeaderRuntimeSlot.tsx` and `runtimeParamSegmented.tsx` do not exist and Dashboard has no title slot.

- [ ] **Step 3: Add the context-backed header target**

Create `widgetHeaderRuntimeSlot.tsx` with this public shape:

```tsx
'use client';

import React, { createContext, useContext, useState } from 'react';

const WidgetHeaderRuntimeSlotContext = createContext<HTMLElement | null>(null);

export const useWidgetHeaderRuntimeSlot = () =>
  useContext(WidgetHeaderRuntimeSlotContext);

export const WidgetHeaderRuntimeSlotProvider: React.FC<{
  children: (
    slotRef: React.Dispatch<React.SetStateAction<HTMLElement | null>>,
  ) => React.ReactNode;
}> = ({ children }) => {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  return (
    <WidgetHeaderRuntimeSlotContext.Provider value={target}>
      {children(setTarget)}
    </WidgetHeaderRuntimeSlotContext.Provider>
  );
};
```

The context stores only the DOM target; it must not store the runtime option value.

- [ ] **Step 4: Put the slot in the Dashboard title row**

Wrap each `renderWidgetCard` result with `WidgetHeaderRuntimeSlotProvider`. Between the truncating title block and edit menu render:

```tsx
<div
  ref={runtimeSlotRef}
  className="no-drag ml-auto max-w-[70%] shrink-0 overflow-x-auto"
/>
```

Keep the title block as `flex-1 min-w-0` and its `<h4>` as `truncate`. The slot is empty for non-TopN and historical TopN widgets, so it must contribute no fixed width of its own.

- [ ] **Step 5: Extract one reusable Segmented renderer**

Create `runtimeParamSegmented.tsx`:

```tsx
'use client';

import React from 'react';
import { Segmented } from 'antd';
import type {
  RuntimeParamControl,
  RuntimeParamValue,
} from '@/app/ops-analysis/types/dashBoard';
import {
  getRuntimeParamSegmentedOptions,
  hasRuntimeParamSegmentedValue,
} from '@/app/ops-analysis/utils/runtimeParamControl';

interface RuntimeParamSegmentedProps {
  control?: RuntimeParamControl;
  value?: RuntimeParamValue;
  onChange?: (value: RuntimeParamValue) => void;
  block?: boolean;
}

const RuntimeParamSegmented: React.FC<RuntimeParamSegmentedProps> = ({
  control,
  value,
  onChange,
  block = false,
}) => {
  const options = getRuntimeParamSegmentedOptions(control);
  if (!options.length || !hasRuntimeParamSegmentedValue(control, value)) {
    return null;
  }

  return (
    <Segmented
      block={block}
      className="min-w-max"
      options={options}
      value={value}
      onChange={(nextValue) => onChange?.(nextValue as RuntimeParamValue)}
    />
  );
};

export default RuntimeParamSegmented;
```

- [ ] **Step 6: Portal the instance-owned control from WidgetWrapper**

In `widgetDataRenderer.tsx`, read `headerRuntimeSlot = useWidgetHeaderRuntimeSlot()`. Build a portal using the existing `config.runtimeParamControl`, `runtimeParamValue`, and `setRuntimeParamValue`:

```tsx
const runtimeHeaderControl =
  chartType === 'topN' && headerRuntimeSlot
    ? createPortal(
        <RuntimeParamSegmented
          control={config?.runtimeParamControl}
          value={runtimeParamValue}
          onChange={setRuntimeParamValue}
        />,
        headerRuntimeSlot,
      )
    : null;
```

Render this portal alongside the initial loading/error content as well as the final `WidgetRenderer`. Pass `runtimeParamControlPlacement={headerRuntimeSlot ? 'header' : 'inline'}` to `WidgetRenderer`. Do not add runtime state to the slot context.

- [ ] **Step 7: Keep inline fallback without duplicate controls**

Extend the TopN conditional props in `widgetRenderer.tsx` with `runtimeParamControlPlacement`. In `ComTopN`, replace its direct AntD `Segmented` import/rendering with `RuntimeParamSegmented` and render it only when:

```tsx
runtimeParamControlPlacement !== 'header'
```

The inline fallback remains in the existing top section for Screen/Topology or any container without a header slot. Dashboard must render only the portal copy.

- [ ] **Step 8: Preserve the Story as a narrow-layout check**

Update the existing runtime-dimension Story so its Dashboard-like preview header contains a bounded right slot or a documented narrow frame using `RuntimeParamSegmented`. Keep three options, long text, independent local state, and `topNValueField: 'total_cost'`.

- [ ] **Step 9: Run GREEN verification**

Run:

```powershell
cd web
pnpm test:ops-analysis-topn-runtime-param
```

Expected: PASS with `ops analysis TopN runtime parameter tests passed`.

Run focused TypeScript/ESLint checks available in the repository and report unrelated existing failures separately. Do not claim Storybook passed if the known Webpack `WasmHash` blocker remains.

- [ ] **Step 10: Review checkpoint**

Verify from the diff that:

- Dashboard shows only the header Portal control.
- Title truncates before the control moves or wraps.
- Header control is present during initial loading, retry/error, empty, and rows.
- Historical/no-control TopN and non-TopN cards leave the slot empty.
- Screen/Topology retain the inline fallback.
- Runtime value remains per `WidgetWrapper` instance and no request/cache code changed.
- No staging or commit operation occurred.

---

## Plan Self-Review

- **Spec coverage:** The single task covers the Dashboard header slot, title truncation, bounded right control, content-state visibility, historical compatibility, and inline fallback.
- **Placeholder scan:** No TBD, TODO, deferred implementation, or unspecified test command remains.
- **Type consistency:** The plan reuses existing `RuntimeParamControl` and `RuntimeParamValue`; the only new placement type is `'header' | 'inline'` across WidgetWrapper, WidgetRenderer, and ComTopN.
- **Scope:** No backend, datasource protocol, configuration sidebar, request, cache, ranking, or global Dashboard state change is included.
- **Authorization:** All commit/staging steps are intentionally omitted because the user explicitly prohibited unauthorized commits.
