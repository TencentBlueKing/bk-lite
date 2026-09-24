import type { WorkflowCanvasMetadata } from './canvas-dsl';
import type { ConductorDefinition, WorkflowRecord } from './types';

const pad = (value: number, length = 2) => String(value).padStart(length, '0');

export function createDefaultWorkflowName(now = new Date(), prefix = '流程'): string {
  return `${prefix}${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}${pad(now.getMilliseconds(), 3)}`;
}

export function createDuplicateWorkflowName(name: string, suffix = '（副本）'): string {
  return `${name.slice(0, Math.max(0, 120 - suffix.length))}${suffix}`;
}

export function createUnsavedWorkflowDraft(name: string, labels: { riskSummary: string } = {
  riskSummary: '空白流程，尚未添加节点。',
}): {
  workflow: WorkflowRecord;
  definition: ConductorDefinition;
  metadata: WorkflowCanvasMetadata;
} {
  const definition: ConductorDefinition = {
    name: 'workflow_draft',
    description: '',
    version: 1,
    schemaVersion: 2,
    ownerEmail: 'bklite@weops.com',
    inputParameters: [],
    outputParameters: {},
    tasks: [],
    restartable: true,
    workflowStatusListenerEnabled: false,
  };
  const inputSchema = { type: 'object' as const, properties: {}, required: [] as string[], additionalProperties: false };
  const metadata: WorkflowCanvasMetadata = {
    trigger_nodes: [],
    return_nodes: [],
    edges: [],
    input_schema: inputSchema,
    data_contract: { version: 1, systemContextVersion: 1, inputs: [], constants: [], outputs: [] },
    risk_summary: { level: 'low', description: labels.riskSummary },
  };
  return {
    definition,
    metadata,
    workflow: {
      id: 0,
      name,
      description: '',
      status: 'DRAFT',
      current_version: 0,
      enabled: false,
      has_draft: true,
      draft_revision: 0,
      draft_base_version: 0,
      definition,
      canvas_metadata: metadata,
      engine_name: '',
      created_by: '',
      updated_by: '',
      created_at: '',
      updated_at: '',
    },
  };
}
