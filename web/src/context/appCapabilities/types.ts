import type { ComponentType } from 'react';

export interface AppSlotContribution {
  key: string;
  labelKey: string;
  labelDefault: string;
  component: ComponentType<any>;
}

export interface AppCapabilityModule {
  slots?: Record<string, AppSlotContribution>;
}

export type AppCapabilityStatus = 'unavailable' | 'loading' | 'ready';

export type AppCapabilityState<T> =
  | { status: 'unavailable'; api?: undefined }
  | { status: 'loading'; api?: undefined }
  | { status: 'ready'; api: T };
