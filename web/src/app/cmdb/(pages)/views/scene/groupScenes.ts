export type SceneVisibility = 'personal' | 'organization' | 'global';

export interface SceneViewRecord {
  id: number;
  name: string;
  visibility: SceneVisibility;
  organization?: number | null;
  model_ids: string[];
  tags: string[];
  tag_match: 'and' | 'or';
  created_by?: string;
  can_edit?: boolean;
}

export const SCENE_GROUP_ORDER: readonly SceneVisibility[] = [
  'personal',
  'organization',
  'global',
];

export const isSceneVisibility = (value: string): value is SceneVisibility =>
  value === 'personal' || value === 'organization' || value === 'global';

export const groupSceneViews = (
  scenes: SceneViewRecord[]
): Array<{ key: SceneVisibility; items: SceneViewRecord[] }> => {
  const buckets: Record<SceneVisibility, SceneViewRecord[]> = {
    personal: [],
    organization: [],
    global: [],
  };
  for (const scene of scenes) {
    if (!isSceneVisibility(scene.visibility)) continue;
    buckets[scene.visibility].push(scene);
  }
  return SCENE_GROUP_ORDER.filter((key) => buckets[key].length > 0).map((key) => ({
    key,
    items: buckets[key],
  }));
};
