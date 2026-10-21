import type { JsonSchema } from './types';

const WORKFLOW_INPUT_REFERENCE = /\$\{workflow\.input\.([A-Za-z_][A-Za-z0-9_]*)/g;

export function jobTargetOperatingSystems(options: {
  targets: unknown;
  triggers: Array<{ input_schema?: JsonSchema }>;
}): Array<'linux' | 'windows'> | undefined {
  if (typeof options.targets !== 'string') return undefined;
  const allowed = new Set<'linux' | 'windows'>();
  let referenced = false;
  for (const match of options.targets.matchAll(WORKFLOW_INPUT_REFERENCE)) {
    const key = match[1];
    for (const trigger of options.triggers) {
      const operatingSystems = trigger.input_schema?.properties?.[key]?.['x-target-binding']?.allowedOperatingSystems;
      if (!operatingSystems?.length) continue;
      referenced = true;
      operatingSystems.forEach((item) => allowed.add(item));
    }
  }
  return referenced ? [...allowed] : undefined;
}
