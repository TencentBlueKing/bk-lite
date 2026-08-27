import type { RackRoomMode, ViewType } from './viewTypes';

export const resolveRackRoomMode = (
  modelId: string,
  mode?: RackRoomMode
): RackRoomMode | null => {
  if (modelId === 'server_room') return 'room';
  if (modelId === 'rack') return 'rack';
  return mode ?? null;
};

export const viewAllowsMultiSelect = (
  viewType: ViewType,
  mode?: RackRoomMode
): boolean => viewType === 'rack-room' && mode === 'rack';

export const eligibleModelIdsForView = (
  viewType: ViewType,
  mode?: RackRoomMode
): string[] => {
  switch (viewType) {
    case 'k8s':
      return ['k8s_cluster'];
    case 'ip':
      return ['subnet'];
    case 'application':
      return ['system', 'application'];
    case 'rack-room':
      return mode === 'rack' ? ['rack'] : ['server_room'];
    case 'network':
      return [];
    default:
      return [];
  }
};

export const isViewEligible = (
  viewType: ViewType,
  modelId: string,
  themes: string[],
  mode?: RackRoomMode
): boolean => {
  switch (viewType) {
    case 'network':
      return themes.includes('network');
    case 'ip':
      return themes.includes('ipam') || modelId === 'subnet';
    case 'application':
      return themes.includes('app_overview');
    case 'k8s':
      return modelId === 'k8s_cluster';
    case 'rack-room': {
      if (mode === 'room') return modelId === 'server_room';
      if (mode === 'rack') return modelId === 'rack';
      return false;
    }
    default:
      return false;
  }
};
