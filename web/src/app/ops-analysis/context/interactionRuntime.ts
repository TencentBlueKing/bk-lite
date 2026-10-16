'use client';

import { useSyncExternalStore } from 'react';

import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { InteractionSurface } from '@/app/ops-analysis/utils/interactionLink';

export interface InteractionRuntimeSnapshot {
  surface: InteractionSurface;
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
}

const EMPTY_RUNTIME: InteractionRuntimeSnapshot = {
  surface: 'edit',
  definitions: [],
  values: {},
};

interface RuntimeEntry {
  owner: string;
  snapshot: InteractionRuntimeSnapshot;
}

let stack: RuntimeEntry[] = [];
let currentRuntime = EMPTY_RUNTIME;
const listeners = new Set<() => void>();

const publish = (next: InteractionRuntimeSnapshot) => {
  currentRuntime = next;
  listeners.forEach((listener) => listener());
};

export const setInteractionRuntime = (
  next: InteractionRuntimeSnapshot,
  owner: string,
) => {
  stack = stack.filter((entry) => entry.owner !== owner);
  stack.push({ owner, snapshot: next });
  publish(next);
};

export const resetInteractionRuntime = (owner?: string) => {
  if (owner === undefined) {
    stack = [];
    publish(EMPTY_RUNTIME);
    return;
  }
  const nextStack = stack.filter((entry) => entry.owner !== owner);
  if (nextStack.length === stack.length) return;
  stack = nextStack;
  publish(stack.length ? stack[stack.length - 1].snapshot : EMPTY_RUNTIME);
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export const readInteractionRuntime = () => currentRuntime;

export const useInteractionRuntime = () =>
  useSyncExternalStore(subscribe, readInteractionRuntime, () => EMPTY_RUNTIME);
