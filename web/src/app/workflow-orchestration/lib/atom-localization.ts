import type { AtomCatalogItem, JsonSchema } from './types';

type Translate = (id: string, defaultMessage?: string) => string;

function localizeSchema(schema: JsonSchema | undefined, prefix: string, t: Translate): JsonSchema | undefined {
  if (!schema?.properties) return schema;
  return {
    ...schema,
    properties: Object.fromEntries(Object.entries(schema.properties).map(([key, field]) => [
      key,
      {
        ...field,
        ...(field.title ? { title: t(`${prefix}.${key}`, field.title) } : {}),
      },
    ])),
  };
}

export function localizeAtom<T extends Pick<AtomCatalogItem, 'key' | 'name' | 'category' | 'description' | 'input_schema' | 'output_schema'>>(
  atom: T,
  t: Translate,
): T {
  const prefix = `workflowOrchestration.atom.catalog.${atom.key}`;
  return {
    ...atom,
    name: t(`${prefix}.name`, atom.name),
    category: t(`${prefix}.category`, atom.category),
    description: t(`${prefix}.description`, atom.description),
    input_schema: localizeSchema(atom.input_schema, `${prefix}.input`, t),
    output_schema: localizeSchema(atom.output_schema, `${prefix}.output`, t),
  };
}
