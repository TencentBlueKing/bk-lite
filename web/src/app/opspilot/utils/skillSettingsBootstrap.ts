import type { LlmModel, SkillPackage, SkillPackageListResponse } from '@/app/opspilot/types/skill';
import type { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';

export const getSkillPackageKey = (pkg: Pick<SkillPackage, 'id' | 'package_id' | 'version'>) =>
  String(pkg.id || `${pkg.package_id}:${pkg.version}`);

export const mergeSkillPackageCatalog = (
  catalog: SkillPackage[],
  selected: SkillPackage[],
): SkillPackage[] => {
  const byKey = new Map<string, SkillPackage>();
  for (const pkg of catalog) {
    byKey.set(getSkillPackageKey(pkg), pkg);
  }
  for (const pkg of selected) {
    const key = getSkillPackageKey(pkg);
    if (!byKey.has(key)) {
      byKey.set(key, pkg);
    }
  }
  return Array.from(byKey.values());
};

const fulfilledOr = <T>(result: PromiseSettledResult<T>, fallback: T): T =>
  result.status === 'fulfilled' ? result.value : fallback;

export const loadSkillSettingsAuxiliary = async (loaders: {
  fetchLlmModels: () => Promise<LlmModel[]>;
  fetchSkillPackages: () => Promise<SkillPackageListResponse>;
  fetchKnowledgeBases: () => Promise<WikiKnowledgeBase[]>;
}): Promise<{
  llmModels: LlmModel[];
  skillPackages: SkillPackage[];
  knowledgeBases: WikiKnowledgeBase[];
}> => {
  const [llmResult, pkgResult, wikiResult] = await Promise.allSettled([
    loaders.fetchLlmModels(),
    loaders.fetchSkillPackages(),
    loaders.fetchKnowledgeBases(),
  ]);
  const models = fulfilledOr(llmResult, [] as LlmModel[]);
  const packages = fulfilledOr(pkgResult, { items: [], count: 0 });
  const knowledgeBases = fulfilledOr(wikiResult, [] as WikiKnowledgeBase[]);
  return {
    llmModels: Array.isArray(models) ? models : [],
    skillPackages: packages.items || [],
    knowledgeBases: Array.isArray(knowledgeBases) ? knowledgeBases : [],
  };
};
