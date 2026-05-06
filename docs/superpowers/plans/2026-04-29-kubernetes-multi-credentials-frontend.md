# Kubernetes Multi-Credentials Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the OpsPilot Kubernetes tool editor save and validate multi-instance kubeconfig credentials using only `kubernetes_instances`, with no default-instance frontend semantics.

**Architecture:** Keep the existing two-panel Kubernetes editor UI and align its parsing, validation, and serialization behavior with the existing multi-instance tool editors such as MySQL. Preserve backward-compatible reads from legacy `kubeconfig_data`, but converge all saves to the array-based contract.

**Tech Stack:** Next.js, React 19, TypeScript, Ant Design, existing OpsPilot i18n JSON locales.

---

### Task 1: Update Kubernetes tool parsing and serialization

**Files:**
- Modify: `web/src/app/opspilot/components/skill/toolSelector.tsx`

- [ ] **Step 1: Add the failing behavior check in code review form**

Confirm the current Kubernetes serializer still emits the removed compatibility field:

```ts
return [
  { key: KUBERNETES_INSTANCES_KEY, value: JSON.stringify(normalized) },
  { key: KUBERNETES_DEFAULT_INSTANCE_ID_KEY, value: normalized[0]?.id || '' },
];
```

Expected: the file still writes `kubernetes_default_instance_id`, which no longer matches the backend contract.

- [ ] **Step 2: Remove the obsolete default-instance constant and serializer output**

Change the Kubernetes serializer to only emit the array payload:

```ts
const serializeKubernetesToolConfig = (instances: KubernetesInstanceFormValue[]): ToolVariable[] => {
  const normalized = instances.map((instance) => {
    const copy = { ...instance };
    delete copy.testStatus;
    return copy;
  });

  return [{ key: KUBERNETES_INSTANCES_KEY, value: JSON.stringify(normalized) }];
};
```

- [ ] **Step 3: Keep legacy parsing compatibility**

Ensure the parser still supports both:

```ts
const instancesValue = kwargsMap.get(KUBERNETES_INSTANCES_KEY);
const parsedInstances = parseKubernetesInstancesValue(instancesValue);
```

and legacy fallback:

```ts
const hasLegacyConfig = ['kubeconfig_data'].some((key) => kwargsMap.has(key));
```

Expected: old single-kubeconfig records still open correctly in the editor.

### Task 2: Add Kubernetes save validation matching other multi-instance tools

**Files:**
- Modify: `web/src/app/opspilot/components/skill/toolSelector.tsx`

- [ ] **Step 1: Add Kubernetes validation branch in `handleEditModalOk()`**

Implement the same shape used by MySQL and Redis, adapted for kubeconfig:

```ts
if (isKubernetesTool(editingTool)) {
  const trimmedNames = kubernetesInstances.map((instance) => instance.name.trim()).filter(Boolean);
  if (kubernetesInstances.length === 0) {
    message.error(t('tool.kubernetes.noInstances'));
    return;
  }
  if (trimmedNames.length !== kubernetesInstances.length) {
    message.error(t('tool.kubernetes.instanceNameRequired'));
    return;
  }
  if (new Set(trimmedNames).size !== trimmedNames.length) {
    message.error(t('tool.kubernetes.duplicateInstanceName'));
    return;
  }
  if (kubernetesInstances.some((instance) => !instance.kubeconfig_data.trim())) {
    message.error(t('tool.kubernetes.kubeconfigDataRequired'));
    return;
  }
}
```

- [ ] **Step 2: Save trimmed instance values back into selected tools**

Persist normalized data in the same branch:

```ts
const updatedTool = {
  ...editingTool,
  kwargs: serializeKubernetesToolConfig(
    kubernetesInstances.map((instance) => ({
      ...instance,
      name: instance.name.trim(),
      kubeconfig_data: instance.kubeconfig_data.trim(),
    })),
  ),
};
```

- [ ] **Step 3: Close modal and clear editor state after save**

Use the same completion flow as the other tool branches:

```ts
setSelectedTools(updatedSelectedTools);
onChange(updatedSelectedTools);
setEditModalVisible(false);
setEditingTool(null);
return;
```

### Task 3: Refine Kubernetes editor behavior and locale coverage

**Files:**
- Modify: `web/src/app/opspilot/components/skill/kubernetesToolEditor.tsx`
- Modify: `web/src/app/opspilot/locales/zh.json`
- Modify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: Keep editor semantics focused on instance list only**

Do not add any default-instance selector or badge. Keep the component API unchanged and preserve the two-panel layout.

- [ ] **Step 2: Confirm per-instance edits reset test status**

Retain the current instance change behavior in `toolSelector.tsx`:

```ts
instance.id === instanceId ? { ...instance, [field]: value, testStatus: 'untested' } : instance
```

Expected: editing kubeconfig or instance name invalidates previous test status.

- [ ] **Step 3: Add missing locale keys used by Kubernetes validation and editor states**

Ensure both locale files contain keys for:

```json
"noInstances": "...",
"instanceNameRequired": "...",
"duplicateInstanceName": "...",
"kubeconfigDataRequired": "...",
"selectInstance": "..."
```

Expected: no raw i18n keys appear in the UI during save or empty states.

### Task 4: Verify the frontend changes

**Files:**
- Verify: `web/src/app/opspilot/components/skill/toolSelector.tsx`
- Verify: `web/src/app/opspilot/components/skill/kubernetesToolEditor.tsx`
- Verify: `web/src/app/opspilot/locales/zh.json`
- Verify: `web/src/app/opspilot/locales/en.json`

- [ ] **Step 1: Run lint**

Run: `pnpm lint`

Expected: no ESLint errors caused by the Kubernetes frontend changes.

- [ ] **Step 2: Run type-check**

Run: `pnpm type-check`

Expected: TypeScript passes without type errors caused by the Kubernetes frontend changes.

- [ ] **Step 3: Re-read the changed code against the spec**

Confirm the implementation satisfies all of the following:

```md
- saves only `kubernetes_instances`
- still reads legacy `kubeconfig_data`
- validates non-empty unique names
- validates non-empty kubeconfig data
- keeps single-instance connection testing
- exposes no default-instance frontend semantics
```
