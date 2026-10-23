import type { AtomCatalogItem, JsonSchema } from './types';

type Translate = (id: string, defaultMessage?: string) => string;

function localizeField(field: JsonSchema, keyPath: string, t: Translate): JsonSchema {
  const next: JsonSchema = {
    ...field,
    ...(field.title ? { title: t(keyPath, field.title) } : {}),
  };
  if (field.properties) {
    next.properties = Object.fromEntries(Object.entries(field.properties).map(([key, child]) => [
      key,
      localizeField(child, `${keyPath}.${key}`, t),
    ]));
  }
  if (field.items && typeof field.items === 'object' && !Array.isArray(field.items)) {
    if (field.items.properties) {
      next.items = {
        ...field.items,
        ...(field.items.title ? { title: t(`${keyPath}.items`, field.items.title) } : {}),
        properties: Object.fromEntries(Object.entries(field.items.properties).map(([key, child]) => [
          key,
          localizeField(child, `${keyPath}.${key}`, t),
        ])),
      };
    } else {
      next.items = localizeField(field.items, `${keyPath}.items`, t);
    }
  }
  return next;
}

function localizeSchema(schema: JsonSchema | undefined, prefix: string, t: Translate): JsonSchema | undefined {
  if (!schema?.properties) return schema;
  return localizeField(schema, prefix, t);
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
