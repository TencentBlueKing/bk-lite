import { resolveNodeTestInputs } from './data-references';
import type { ConductorTask, JsonSchema } from './types';

const NODE_OVERRIDE_PREFIX = '__node_input__';
const WORKFLOW_INPUT_REFERENCE = /\$\{workflow\.input\.([A-Za-z_][A-Za-z0-9_]*)[^}]*}/g;

export interface NodeTestInputContract {
  schema: JsonSchema;
  nodeOverrides: Record<string, string>;
}

function cloneSchema(schema: JsonSchema): JsonSchema {
  return JSON.parse(JSON.stringify(schema)) as JsonSchema;
}

function workflowInputFields(value: unknown, result = new Set<string>()) {
  if (Array.isArray(value)) {
    value.forEach((item) => workflowInputFields(item, result));
    return result;
  }
  if (value && typeof value === 'object') {
    Object.values(value).forEach((item) => workflowInputFields(item, result));
    return result;
  }
  if (typeof value !== 'string') return result;
  for (const match of value.matchAll(WORKFLOW_INPUT_REFERENCE)) result.add(match[1]);
  return result;
}

function hasConfiguredValue(value: unknown) {
  return value !== undefined && value !== null && value !== '' && (!Array.isArray(value) || value.length > 0);
}

function jobTargetSchema(schema: JsonSchema): JsonSchema {
  if (schema['x-target-binding']) {
    return {
      ...schema,
      'x-target-binding': {
        ...schema['x-target-binding'],
        allowedSources: schema['x-target-binding'].allowedSources?.length
          ? schema['x-target-binding'].allowedSources
          : ['job_mgmt'],
      },
    };
  }
  return {
    ...schema,
    'x-widget': 'target-selector',
    'x-target-binding': {
      mode: 'runtime',
      allowedSources: ['job_mgmt'],
      allowedOperatingSystems: ['linux', 'windows'],
      minCount: Math.max(1, schema.minItems || 1),
      maxCount: schema.maxItems || 100,
    },
  };
}

export function buildNodeTestInputContract(
  task: ConductorTask | undefined,
  atomInputSchema: JsonSchema | undefined,
  triggerInputSchema: JsonSchema | undefined,
): NodeTestInputContract {
  if (!task || task.type !== 'SIMPLE') return { schema: { type: 'object', properties: {}, required: [], additionalProperties: false }, nodeOverrides: {} };

  const properties: Record<string, JsonSchema> = {};
  const required = new Set<string>();
  const nodeOverrides: Record<string, string> = {};
  const taskInputs = task.inputParameters || {};
  const triggerProperties = triggerInputSchema?.properties || {};

  for (const field of workflowInputFields(taskInputs)) {
    const triggerField = triggerProperties[field];
    if (!triggerField) continue;
    const usedByJobTargets = task.name === 'bklite_job_execute'
      && workflowInputFields(taskInputs.targets).has(field);
    properties[field] = usedByJobTargets ? jobTargetSchema(cloneSchema(triggerField)) : cloneSchema(triggerField);
    required.add(field);
  }

  for (const field of atomInputSchema?.required || []) {
    const configured = taskInputs[field];
    const referencedWorkflowFields = workflowInputFields(configured);
    const referencesMissingTriggerField = referencedWorkflowFields.size > 0
      && [...referencedWorkflowFields].every((key) => !triggerProperties[key]);
    const jobTargetsNeedConfirmation = task.name === 'bklite_job_execute'
      && field === 'targets'
      && Array.isArray(configured)
      && configured.every((item) => typeof item === 'string');
    if (hasConfiguredValue(configured) && !referencesMissingTriggerField && !jobTargetsNeedConfirmation) continue;
    const fieldSchema = atomInputSchema?.properties?.[field];
    if (!fieldSchema) continue;
    const testField = `${NODE_OVERRIDE_PREFIX}${field}`;
    properties[testField] = task.name === 'bklite_job_execute' && field === 'targets'
      ? jobTargetSchema(cloneSchema(fieldSchema))
      : cloneSchema(fieldSchema);
    nodeOverrides[testField] = field;
    required.add(testField);
  }

  return {
    schema: {
      type: 'object',
      properties,
      required: [...required],
      additionalProperties: false,
    },
    nodeOverrides,
  };
}

export function materializeNodeTestInputs(
  contract: NodeTestInputContract,
  taskInputs: Record<string, unknown>,
  testInputs: Record<string, unknown>,
  nodeOutputs: Record<string, unknown>,
) {
  const syntheticFields = new Set(Object.keys(contract.nodeOverrides));
  const workflowFields = new Set(Object.keys(contract.schema.properties || {}).filter((key) => !syntheticFields.has(key)));
  const workflowInputs = Object.fromEntries(Object.entries(testInputs).filter(([key]) => workflowFields.has(key)));
  const resolved = resolveNodeTestInputs(taskInputs, workflowInputs, nodeOutputs);
  const nodeInputs = { ...resolved.value };
  for (const [testField, nodeField] of Object.entries(contract.nodeOverrides)) {
    if (testInputs[testField] !== undefined) nodeInputs[nodeField] = testInputs[testField];
  }
  return { workflowInputs, nodeInputs, unresolved: resolved.unresolved };
}
