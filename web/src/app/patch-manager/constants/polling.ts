import type { ListItem } from '@/types';

export const PATCH_MANAGER_POLL_INTERVAL_MS = 5000;

export const PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS = 0;

export const createPatchManagerPollFrequencyOptions = (offLabel: string): ListItem[] => [
  { label: offLabel, value: PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS },
  { label: '5s', value: PATCH_MANAGER_POLL_INTERVAL_MS },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];
