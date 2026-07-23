'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import type {
  CreateIncidentIMGroupParams,
  IncidentIMGroup,
  IncidentIMGroupOptions,
  IncidentIMMemberList,
  IncidentIMMemberListParams,
} from '@/app/alarm/types/incidents';
import { createPollScheduler, ownsIMGroupResponse } from './controller';
import { deriveIMGroupView, getIMGroupPollDelay } from './state';

export type IMGroupActionKey =
  | 'create'
  | 'retry'
  | 'pause'
  | 'resume'
  | 'settings'
  | 'unlink';

interface UseIncidentIMGroupOptions {
  incidentPk: string;
  refreshVersion: number;
}

export const useIncidentIMGroup = ({
  incidentPk,
  refreshVersion,
}: UseIncidentIMGroupOptions) => {
  const api = useIncidentsApi();
  const apiRef = useRef(api);
  apiRef.current = api;
  const incidentPkRef = useRef(incidentPk);
  incidentPkRef.current = incidentPk;

  const [group, setGroup] = useState<IncidentIMGroup | null>(null);
  const groupRef = useRef<IncidentIMGroup | null>(null);
  groupRef.current = group;
  const [groupLoading, setGroupLoading] = useState(true);
  const [groupError, setGroupError] = useState(false);
  const [options, setOptions] = useState<IncidentIMGroupOptions | null>(null);
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [actionLoadingKey, setActionLoadingKey] = useState<IMGroupActionKey | null>(null);
  const [memberLoading, setMemberLoading] = useState(false);

  const groupAbortRef = useRef<AbortController | null>(null);
  const optionsAbortRef = useRef<AbortController | null>(null);
  const memberAbortRef = useRef<AbortController | null>(null);
  const pollStartedAtRef = useRef(Date.now());
  const schedulerRef = useRef(createPollScheduler({
    setTimer: (callback, delay) => window.setTimeout(callback, delay),
    clearTimer: timerId => window.clearTimeout(timerId),
  }));

  const acceptGroup = useCallback((
    value: IncidentIMGroup | null,
    requestedIncidentPk: string,
    requestedGroupId: string | null,
    controller: AbortController,
  ) => {
    if (
      controller.signal.aborted
      || !ownsIMGroupResponse(
        incidentPkRef.current,
        requestedIncidentPk,
        groupRef.current?.id ?? null,
        requestedGroupId,
      )
    ) return false;
    groupRef.current = value;
    setGroup(value);
    setGroupError(false);
    return true;
  }, []);

  const refreshGroup = useCallback(async (silent = false) => {
    if (!incidentPk) return null;
    groupAbortRef.current?.abort();
    const controller = new AbortController();
    groupAbortRef.current = controller;
    const requestedIncidentPk = incidentPk;
    const requestedGroupId = groupRef.current?.id ?? null;
    if (!silent) setGroupLoading(true);
    try {
      const value = await apiRef.current.getIncidentIMGroup(requestedIncidentPk);
      acceptGroup(value, requestedIncidentPk, requestedGroupId, controller);
      return value;
    } catch (error) {
      if (!controller.signal.aborted && incidentPkRef.current === requestedIncidentPk) {
        setGroupError(true);
      }
      throw error;
    } finally {
      if (!controller.signal.aborted && incidentPkRef.current === requestedIncidentPk) {
        setGroupLoading(false);
      }
    }
  }, [acceptGroup, incidentPk]);

  const loadOptions = useCallback(async (channelId?: number) => {
    const requestedIncidentPk = incidentPk;
    optionsAbortRef.current?.abort();
    const controller = new AbortController();
    optionsAbortRef.current = controller;
    setOptionsLoading(true);
    try {
      const value = await apiRef.current.getIncidentIMGroupOptions(requestedIncidentPk, channelId);
      if (!controller.signal.aborted && incidentPkRef.current === requestedIncidentPk) setOptions(value);
      return value;
    } finally {
      if (!controller.signal.aborted && incidentPkRef.current === requestedIncidentPk) {
        setOptionsLoading(false);
      }
    }
  }, [incidentPk]);

  const runGroupAction = useCallback(async (
    key: IMGroupActionKey,
    action: () => Promise<IncidentIMGroup | void>,
  ) => {
    const requestedIncidentPk = incidentPkRef.current;
    const requestedGroupId = groupRef.current?.id ?? null;
    setActionLoadingKey(key);
    try {
      const value = await action();
      if (
        !ownsIMGroupResponse(
          incidentPkRef.current,
          requestedIncidentPk,
          groupRef.current?.id ?? null,
          requestedGroupId,
        )
      ) return value;
      if (value) {
        groupRef.current = value;
        setGroup(value);
      } else {
        groupRef.current = null;
        setGroup(null);
      }
      return value;
    } finally {
      setActionLoadingKey(null);
    }
  }, []);

  const createGroup = useCallback(async (params: CreateIncidentIMGroupParams) => {
    setCreateLoading(true);
    pollStartedAtRef.current = Date.now();
    try {
      const value = await apiRef.current.createIncidentIMGroup(incidentPk, params);
      const controller = new AbortController();
      acceptGroup(value, incidentPk, null, controller);
      return value;
    } catch (error) {
      // A timeout can happen after the idempotent request was accepted. Refresh first.
      try {
        await refreshGroup(true);
      } catch {
        // Preserve and rethrow the original create error.
      }
      throw error;
    } finally {
      setCreateLoading(false);
    }
  }, [acceptGroup, incidentPk, refreshGroup]);

  const getMembers = useCallback(async (params: IncidentIMMemberListParams) => {
    memberAbortRef.current?.abort();
    const controller = new AbortController();
    memberAbortRef.current = controller;
    const requestedIncidentPk = incidentPk;
    const requestedGroupId = groupRef.current?.id ?? null;
    setMemberLoading(true);
    try {
      const value = await apiRef.current.getIncidentIMMembers(requestedIncidentPk, params);
      if (
        controller.signal.aborted
        || !ownsIMGroupResponse(
          incidentPkRef.current,
          requestedIncidentPk,
          groupRef.current?.id ?? null,
          requestedGroupId,
        )
      ) return null;
      return value as IncidentIMMemberList;
    } finally {
      if (!controller.signal.aborted) setMemberLoading(false);
    }
  }, [incidentPk]);

  const cancelMemberRequest = useCallback(() => {
    memberAbortRef.current?.abort();
    setMemberLoading(false);
  }, []);

  useEffect(() => {
    setGroup(null);
    groupRef.current = null;
    setOptions(null);
    pollStartedAtRef.current = Date.now();
    void refreshGroup().catch(() => undefined);
  }, [incidentPk, refreshGroup]);

  useEffect(() => {
    if (refreshVersion <= 0) return;
    void refreshGroup(true).catch(() => undefined);
  }, [refreshGroup, refreshVersion]);

  const view = useMemo(() => group ? deriveIMGroupView(group) : null, [group]);

  useEffect(() => {
    const scheduler = schedulerRef.current;
    scheduler.stop();
    if (!group || !view || document.hidden) return scheduler.stop;
    const fastDelay = getIMGroupPollDelay(view, Date.now() - pollStartedAtRef.current, true);
    const delay = fastDelay ?? 15_000;
    scheduler.schedule(() => {
      void refreshGroup(true).catch(() => undefined);
    }, delay);
    return scheduler.stop;
  }, [group, refreshGroup, view]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (!document.hidden) void refreshGroup(true).catch(() => undefined);
      else schedulerRef.current.stop();
    };
    document.addEventListener('visibilitychange', refreshWhenVisible);
    window.addEventListener('focus', refreshWhenVisible);
    return () => {
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      window.removeEventListener('focus', refreshWhenVisible);
    };
  }, [refreshGroup]);

  useEffect(() => () => {
    schedulerRef.current.stop();
    groupAbortRef.current?.abort();
    optionsAbortRef.current?.abort();
    memberAbortRef.current?.abort();
  }, []);

  return {
    group,
    groupLoading,
    groupError,
    options,
    optionsLoading,
    createLoading,
    actionLoadingKey,
    memberLoading,
    refreshGroup,
    loadOptions,
    createGroup,
    getMembers,
    cancelMemberRequest,
    retry: () => runGroupAction('retry', () => apiRef.current.retryIncidentIMGroup(incidentPk)),
    pause: () => runGroupAction('pause', () => apiRef.current.pauseIncidentIMGroup(incidentPk)),
    resume: () => runGroupAction('resume', () => apiRef.current.resumeIncidentIMGroup(incidentPk)),
    updateContinuousSync: (enabled: boolean) =>
      runGroupAction('settings', () => apiRef.current.updateIncidentIMGroup(
        incidentPk,
        { continuous_sync_enabled: enabled },
      )),
    unlink: (groupName: string) =>
      runGroupAction('unlink', () => apiRef.current.unlinkIncidentIMGroup(incidentPk, groupName)),
  };
};

export type IncidentIMGroupController = ReturnType<typeof useIncidentIMGroup>;
