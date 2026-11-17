export interface TemplateToolRef {
  name: string;
}

export interface CatalogToolRef {
  id: number;
  name: string;
  icon?: string;
}

export interface BoundTemplateTool {
  id?: number;
  name: string;
  icon?: string;
  kwargs: [];
}

export function nextTemplateSkillName(baseName: string, takenNames: Iterable<string>): string {
  const taken = new Set(takenNames);
  if (!taken.has(baseName)) {
    return baseName;
  }
  const firstCopy = `${baseName} 副本`;
  if (!taken.has(firstCopy)) {
    return firstCopy;
  }
  let index = 2;
  let candidate = `${baseName} 副本${index}`;
  while (taken.has(candidate)) {
    index += 1;
    candidate = `${baseName} 副本${index}`;
  }
  return candidate;
}

export function bindTemplateTools(templateTools: TemplateToolRef[] | undefined, catalog: CatalogToolRef[]): BoundTemplateTool[] {
  return (templateTools ?? []).map((tool) => {
    const match = catalog.find((item) => item.name === tool.name);
    return {
      ...(match ? { id: match.id, icon: match.icon } : {}),
      name: tool.name,
      kwargs: [],
    };
  });
}

export async function collectSkillNames(
  fetchPage: (page: number, pageSize: number) => Promise<{ items?: { name: string }[]; count?: number }>,
  pageSize = 100,
): Promise<string[]> {
  const names: string[] = [];
  let page = 1;
  let count = 0;
  do {
    const response = await fetchPage(page, pageSize);
    const items = response.items ?? [];
    count = response.count ?? items.length;
    names.push(...items.map((item) => item.name));
    if (items.length === 0) {
      break;
    }
    page += 1;
  } while (names.length < count);
  return names;
}
