import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useDashboardScenePermissionsApi } from '@/app/ops-analysis/api/dashboardScenePermissions';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
} from '@/app/ops-analysis/types/dashBoard';
import { isDashboardWidgetItem } from '@/app/ops-analysis/utils/dashboardGroups';
import { hasAppAccess } from '@/context/appCapabilities/access';
import {
  type DashboardScenePermissionCode,
  isDashboardWidgetUnauthorized,
  resolveDashboardSceneInstUuid,
  resolveDashboardWidgetSceneType,
} from '@/app/ops-analysis/utils/dashboardWidgetAuth';
import {
  createDashboardViewAuthFrozenSnapshot,
  type DashboardViewAuthFrozenSnapshot,
  createScenePermissionResultGate,
  releaseDashboardViewAuthFrozenState,
  buildDataSourcesLicenseSignature,
  stripScenePermissionsForWidgetIds,
} from '@/app/ops-analysis/utils/dashboardViewAuthSnapshot';

export const SCENE_PERMISSION_TIMEOUT_MS = 8000;

interface UseDashboardViewAuthSnapshotOptions {
  layout: DashboardLayoutItem[];
  dataSources: DatasourceItem[];
  dataSourcesReady: boolean;
  isEditMode: boolean;
  /** 当前画布 data_id；切换时解除冻结并等待本画布资源就绪后再冻 */
  canvasDataId?: string | number;
  shareSessionId?: string;
  /** get_client 返回的应用名；未就绪时不要用空列表冻结 */
  authorizedAppNames: readonly string[];
  appAccessReady: boolean;
  enabled: boolean;
}

export const useDashboardViewAuthSnapshot = ({
  layout,
  dataSources,
  dataSourcesReady,
  isEditMode,
  canvasDataId,
  shareSessionId,
  authorizedAppNames,
  appAccessReady,
  enabled,
}: UseDashboardViewAuthSnapshotOptions) => {
  const { checkDashboardScenePermissions } = useDashboardScenePermissionsApi(shareSessionId);
  const [scenePermissions, setScenePermissions] = useState<
    Record<string, DashboardScenePermissionCode>
  >({});
  const scenePermissionsRef = useRef(scenePermissions);

  const commitScenePermissions = useCallback(
    (next: Record<string, DashboardScenePermissionCode>) => {
      scenePermissionsRef.current = next;
      setScenePermissions(next);
    },
    [],
  );

  const [sceneReady, setSceneReady] = useState(false);
  const frozenRef = useRef(false);
  const [frozen, setFrozen] = useState(false);
  const frozenSnapshotRef = useRef<DashboardViewAuthFrozenSnapshot | null>(null);
  const prevIsEditModeRef = useRef(isEditMode);
  const viewAuthScopeKey = `${shareSessionId ?? ''}\0${canvasDataId ?? ''}`;
  const prevViewAuthScopeKeyRef = useRef(viewAuthScopeKey);

  const releaseFrozenState = useCallback(() => {
    releaseDashboardViewAuthFrozenState({
      frozenRef,
      frozenSnapshotRef,
      setFrozen,
    });
  }, []);

  const widgetItems = useMemo(
    () => layout.filter(isDashboardWidgetItem) as DashboardWidgetLayoutItem[],
    [layout],
  );

  const sceneChecks = useMemo(() => {
    const checks = widgetItems
      .map((widget) => {
        const sceneType = resolveDashboardWidgetSceneType(widget);
        if (sceneType !== 'relatedTopology' && sceneType !== 'applicationTopology') {
          return null;
        }
        const instUuid = resolveDashboardSceneInstUuid(widget);
        if (!instUuid) {
          return null;
        }
        return {
          widget_id: widget.i,
          scene_type: sceneType as 'relatedTopology' | 'applicationTopology',
          inst_uuid: instUuid,
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
    return checks;
  }, [widgetItems]);

  const sceneViewAuthSettledRef = useRef(sceneChecks.length === 0);
  const cycleScenePermissionsRef = useRef<Record<string, DashboardScenePermissionCode>>({});
  const dataSourcesRef = useRef(dataSources);
  dataSourcesRef.current = dataSources;
  const dataSourcesLicenseSignature = useMemo(
    () => buildDataSourcesLicenseSignature(dataSources),
    [dataSources],
  );
  const authorizedAppNamesRef = useRef(authorizedAppNames);
  authorizedAppNamesRef.current = authorizedAppNames;
  const authorizedAppSignature = useMemo(
    () => [...authorizedAppNames].sort().join('|'),
    [authorizedAppNames],
  );

  useEffect(() => {
    if (prevViewAuthScopeKeyRef.current === viewAuthScopeKey) {
      return;
    }
    prevViewAuthScopeKeyRef.current = viewAuthScopeKey;
    cycleScenePermissionsRef.current = {};
    commitScenePermissions({});
    releaseFrozenState();
    sceneViewAuthSettledRef.current = sceneChecks.length === 0;
    if (enabled && !isEditMode) {
      setSceneReady(sceneChecks.length === 0);
    }
  }, [
    commitScenePermissions,
    enabled,
    isEditMode,
    releaseFrozenState,
    sceneChecks.length,
    viewAuthScopeKey,
  ]);

  useEffect(() => {
    if (!enabled || isEditMode) {
      setSceneReady(true);
      return undefined;
    }
    if (sceneChecks.length === 0) {
      commitScenePermissions({});
      sceneViewAuthSettledRef.current = true;
      setSceneReady(true);
      return undefined;
    }

    let active = true;
    const resultGate = createScenePermissionResultGate();
    const checkedWidgetIds = sceneChecks.map((item) => item.widget_id);
    releaseFrozenState();
    cycleScenePermissionsRef.current = {};
    commitScenePermissions(
      stripScenePermissionsForWidgetIds(scenePermissionsRef.current, checkedWidgetIds),
    );
    sceneViewAuthSettledRef.current = false;
    setSceneReady(false);

    const settleCycleAsVisible = () => {
      cycleScenePermissionsRef.current = {};
      commitScenePermissions(
        stripScenePermissionsForWidgetIds(scenePermissionsRef.current, checkedWidgetIds),
      );
    };

    const timeout = window.setTimeout(() => {
      if (!active) return;
      resultGate.close();
      settleCycleAsVisible();
      sceneViewAuthSettledRef.current = true;
      setSceneReady(true);
    }, SCENE_PERMISSION_TIMEOUT_MS);

    void checkDashboardScenePermissions(sceneChecks)
      .then((results) => {
        if (!active) {
          return;
        }
        const merged = resultGate.apply(results);
        if (merged) {
          cycleScenePermissionsRef.current = merged;
          commitScenePermissions({
            ...scenePermissionsRef.current,
            ...merged,
          });
        }
      })
      .catch(() => {
        if (!active || !resultGate.isOpen()) {
          return;
        }
        settleCycleAsVisible();
      })
      .finally(() => {
        if (!active) return;
        window.clearTimeout(timeout);
        if (resultGate.isOpen()) {
          sceneViewAuthSettledRef.current = true;
          setSceneReady(true);
        }
      });

    return () => {
      active = false;
      resultGate.close();
      window.clearTimeout(timeout);
    };
  }, [
    checkDashboardScenePermissions,
    enabled,
    isEditMode,
    commitScenePermissions,
    releaseFrozenState,
    sceneChecks,
    viewAuthScopeKey,
  ]);

  const resourcesReady =
    !enabled || isEditMode || (dataSourcesReady && sceneReady && appAccessReady);

  useEffect(() => {
    if (!dataSourcesReady) {
      releaseFrozenState();
    }
  }, [dataSourcesReady, releaseFrozenState]);

  useEffect(() => {
    const leftEditMode = prevIsEditModeRef.current && !isEditMode;
    prevIsEditModeRef.current = isEditMode;

    if (isEditMode) {
      if (frozenRef.current || frozen) {
        releaseFrozenState();
      }
      return;
    }

    if (leftEditMode && sceneChecks.length > 0) {
      sceneViewAuthSettledRef.current = false;
      setSceneReady(false);
      releaseFrozenState();
    }
  }, [frozen, isEditMode, releaseFrozenState, sceneChecks.length]);

  useEffect(() => {
    if (
      isEditMode
      || !enabled
      || !resourcesReady
      || frozenRef.current
      || !sceneViewAuthSettledRef.current
    ) {
      return;
    }
    frozenRef.current = true;
    frozenSnapshotRef.current = createDashboardViewAuthFrozenSnapshot(
      dataSourcesRef.current,
      { ...cycleScenePermissionsRef.current },
      authorizedAppNamesRef.current,
    );
    setFrozen(true);
  }, [
    authorizedAppSignature,
    dataSourcesLicenseSignature,
    enabled,
    isEditMode,
    resourcesReady,
    viewAuthScopeKey,
  ]);

  // 模块许可看当前 payload 和当前身份的应用列表。首屏冻结只稳住场景 ACL，
  // 不能把 lookup 完成前的空 required_app 或尚未到达的访问者应用列表钉死。
  const isWidgetUnauthorized = useCallback(
    (widgetId: string) => {
      if (isEditMode || !frozen) {
        return false;
      }
      const widget = widgetItems.find((item) => item.i === widgetId);
      if (!widget) {
        return false;
      }
      const apps = authorizedAppNames.map((name) => ({ name }));
      return isDashboardWidgetUnauthorized(widget, {
        dataSources,
        hasAppAccess: (appName) => hasAppAccess(apps, appName),
      });
    },
    [authorizedAppNames, dataSources, frozen, isEditMode, widgetItems],
  );

  const isScenePermissionDenied = useCallback(
    (widgetId: string) =>
      frozenSnapshotRef.current?.scenePermissions[widgetId] === 'permission_denied',
    // frozen toggles when snapshot is written; widgetItems stable enough for render
    [frozen],
  );

  return {
    frozen: frozen && !isEditMode,
    scenePermissions: frozenSnapshotRef.current?.scenePermissions ?? scenePermissions,
    isWidgetUnauthorized,
    isScenePermissionDenied,
    resourcesReady,
  };
};
