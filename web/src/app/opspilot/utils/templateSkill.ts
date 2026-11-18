import type { CreateSkillPayload, SkillTemplate } from '@/app/opspilot/types/skill';

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

export function buildTemplateSkillPayload(
  template: SkillTemplate,
  takenNames: Iterable<string>,
  catalog: CatalogToolRef[],
): CreateSkillPayload {
  return {
    name: nextTemplateSkillName(template.name, takenNames),
    introduction: template.introduction,
    skill_type: template.skill_type,
    skill_prompt: template.skill_prompt,
    guide: template.guide,
    enable_conversation_history: template.enable_conversation_history,
    conversation_window_size: template.conversation_window_size,
    run_model_call_limit: template.run_model_call_limit,
    temperature: template.temperature,
    show_think: template.show_think,
    enable_suggest: template.enable_suggest,
    enable_query_rewrite: template.enable_query_rewrite,
    force_wiki_grounded: template.force_wiki_grounded,
    allow_wiki_material_write: template.allow_wiki_material_write,
    memory_write_rounds: template.memory_write_rounds,
    tools: bindTemplateTools(template.tools, catalog),
  };
}
