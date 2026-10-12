"use client";

import React, {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Alert, Button, Empty, Select, Spin } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useParams } from "next/navigation";
import { useTranslation } from "@/utils/i18n";
import { useShareMode } from "@/app/ops-analysis/context/shareMode";
import { useRoom3DApi } from "@/app/ops-analysis/api/room3D";
import { isSceneWidgetAllowedOnSurface } from "@/app/ops-analysis/types/sceneWidgetCapability";
import type { OpsAnalysisWidgetSurface } from "@/app/ops-analysis/utils/chartTypeSurface";
import type { Room3DRoomOption } from "@/app/ops-analysis/types/sceneWidget";
import {
  readPersistedServerRoomId,
  readRoom3DRackTopLines,
  resolveRoom3DSelection,
} from "@/app/ops-analysis/utils/room3DConfig";
import type {
  ScreenRenderContext,
  ValueConfig,
} from "@/app/ops-analysis/types/dashBoard";
import {
  aggregateRackAlarmSummary,
  formatRoom3DDeviceAlarmCountValue,
  formatRoom3DSeverityLabel,
  getRoom3DDisplayOptions,
  getRoom3DPositionLabel,
  getRoom3DRackDevices,
  shouldShowRoom3DDeviceHighestSeverity,
  type Room3DRenderableDevice,
  type Room3DRack,
  type Room3DResponse,
  validateRoom3DData,
} from "./room3DData";
import { createRoom3DScene } from "./room3DScene";
import { loadRoom3DScene } from "./room3DSceneSource";
import styles from "./room3D.module.scss";

interface Room3DProps {
  rawData?: unknown;
  loading?: boolean;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
  surface?: OpsAnalysisWidgetSurface;
  editMode?: boolean;
  refreshKey?: string | number;
  runtimeActive?: boolean;
  onReady?: (ready: boolean) => void;
  onError?: (message: string) => void;
  onRawData?: (data: unknown) => void;
  errorMessage?: string;
}

interface PointerState {
  rack: Room3DRack;
  x: number;
  y: number;
}

interface SizeState {
  width: number;
  height: number;
}

interface SceneReadiness {
  roomData: Room3DResponse;
  rendered: boolean;
}

const Room3D: React.FC<Room3DProps> = ({
  rawData,
  loading: injectedLoading = false,
  config,
  screenRenderContext,
  surface,
  editMode = false,
  refreshKey,
  runtimeActive = true,
  onReady,
  onError,
  onRawData,
  errorMessage: injectedErrorMessage,
}) => {
  const { t } = useTranslation();
  const shareMode = useShareMode();
  const params = useParams<{ sessionId?: string }>();
  const { getRooms, getLayout } = useRoom3DApi(
    shareMode ? params.sessionId : undefined,
  );
  const api = useMemo(
    () => ({ getRooms, getLayout }),
    [getLayout, getRooms],
  );
  const injected = rawData != null;
  const savedRoomId = readPersistedServerRoomId(config);
  const rackTopLines = useMemo(
    () => readRoom3DRackTopLines(config?.room3D),
    [config?.room3D?.rackTopLine1, config?.room3D?.rackTopLine2],
  );
  const roomRef = useRef<HTMLDivElement | null>(null);
  const mountRef = useRef<HTMLDivElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const resetViewRef = useRef<() => void>(() => undefined);
  const resizeSceneRef = useRef<() => void>(() => undefined);
  const sceneReadinessRef = useRef<SceneReadiness | null>(null);
  const [rooms, setRooms] = useState<Room3DRoomOption[]>([]);
  const [runtimeRoomId, setRuntimeRoomId] = useState("");
  const [fetchedLayout, setFetchedLayout] = useState<unknown>(null);
  const [fetchLoading, setFetchLoading] = useState(!injected);
  const [fetchError, setFetchError] = useState("");
  const effectiveRawData = injected ? rawData : fetchedLayout;
  const loading = injected ? injectedLoading : fetchLoading;
  const errorMessage = injected ? injectedErrorMessage : fetchError;
  const validation = useMemo(
    () => validateRoom3DData(effectiveRawData, t),
    [effectiveRawData, t],
  );
  const allowedOnSurface =
    surface == null || isSceneWidgetAllowedOnSurface("room3D", surface);
  const displayOptions = useMemo(
    () => getRoom3DDisplayOptions(config),
    [config],
  );
  const roomData = validation.ok ? validation.data : null;
  const validationError = "error" in validation ? validation.error : "";
  const notice = roomData?.notice;
  const [dismissedNotice, setDismissedNotice] = useState<string | null>(null);
  const visibleNotice = notice && notice !== dismissedNotice ? notice : null;
  const [hoverState, setHoverState] = useState<PointerState | null>(null);
  const [selectedRack, setSelectedRack] = useState<Room3DRack | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<{
    rack: Room3DRack;
    device: Room3DRenderableDevice;
  } | null>(null);
  const [chromeVisible, setChromeVisible] = useState(false);
  const [tooltipSize, setTooltipSize] = useState<SizeState>({
    width: 0,
    height: 0,
  });
  const [sceneRenderVersion, setSceneRenderVersion] = useState(0);

  const isCompact = (screenRenderContext?.widgetDensity || 0) > 0.5;
  const readableOverlayScale = useMemo(() => {
    if (!screenRenderContext?.enabled) {
      return 1;
    }

    const fitScale =
      Number.isFinite(screenRenderContext.fitScale) &&
      screenRenderContext.fitScale > 0
        ? screenRenderContext.fitScale
        : 1;
    const uiScale =
      screenRenderContext.widgetUiScale ||
      screenRenderContext.screenUiScale ||
      1;

    return Math.max(uiScale, 1 / fitScale, 1);
  }, [screenRenderContext]);

  useEffect(() => {
    setRuntimeRoomId("");
  }, [savedRoomId]);

  useEffect(() => {
    if (injected || !runtimeActive || !allowedOnSurface) {
      return undefined;
    }
    const abort = new AbortController();
    setFetchLoading(true);
    setFetchError("");
    loadRoom3DScene({
      api,
      savedRoomId,
      runtimeRoomId,
      signal: abort.signal,
    })
      .then((result) => {
        if (abort.signal.aborted) return;
        setRooms(result.rooms);
        if (result.status === "empty") {
          setFetchedLayout(null);
          setFetchError(t("dashboard.room3DEmpty"));
          onError?.(t("dashboard.room3DEmpty"));
          onRawData?.(null);
          return;
        }
        if (result.status === "unavailable") {
          setFetchedLayout(null);
          setFetchError(t("dashboard.room3DDefaultUnavailable"));
          onError?.(t("dashboard.room3DDefaultUnavailable"));
          onRawData?.(null);
          return;
        }
        setFetchedLayout(result.layout);
        setFetchError("");
        onRawData?.(result.layout);
      })
      .catch(() => {
        if (abort.signal.aborted) return;
        const message = t("dashboard.room3DLoadFailed");
        setFetchedLayout(null);
        setRooms([]);
        setFetchError(message);
        onError?.(message);
        onRawData?.(null);
      })
      .finally(() => {
        if (!abort.signal.aborted) setFetchLoading(false);
      });
    return () => abort.abort();
  }, [
    allowedOnSurface,
    api,
    injected,
    onError,
    onRawData,
    refreshKey,
    runtimeActive,
    runtimeRoomId,
    savedRoomId,
    t,
  ]);

  useEffect(() => {
    setHoverState(null);
    setSelectedRack(null);
    setSelectedDevice(null);
  }, [effectiveRawData]);

  useEffect(() => {
    const mountNode = mountRef.current;
    if (loading || errorMessage || !mountNode || !roomData?.racks.length) {
      sceneReadinessRef.current = null;
      resetViewRef.current = () => undefined;
      resizeSceneRef.current = () => undefined;
      return undefined;
    }

    const readiness: SceneReadiness = { roomData, rendered: false };
    sceneReadinessRef.current = readiness;
    const controller = createRoom3DScene(
      mountNode,
      roomData,
      {
        onHover: setHoverState,
        onFirstRender: () => {
          if (
            sceneReadinessRef.current !== readiness ||
            readiness.rendered
          ) {
            return;
          }
          readiness.rendered = true;
          setSceneRenderVersion((version) => version + 1);
        },
        onSelect: (rack) => {
          setSelectedRack(rack);
          if (!rack) {
            setSelectedDevice(null);
          }
        },
        onDeviceSelect: setSelectedDevice,
      },
      rackTopLines,
    );
    resetViewRef.current = controller.resetView;
    resizeSceneRef.current = controller.resize;

    return () => {
      controller.dispose();
      if (sceneReadinessRef.current === readiness) {
        sceneReadinessRef.current = null;
      }
      resetViewRef.current = () => undefined;
      resizeSceneRef.current = () => undefined;
    };
  }, [errorMessage, loading, rackTopLines, roomData]);

  useEffect(() => {
    if (loading) {
      return;
    }
    const hasScene = Boolean(roomData?.racks.length);
    if (errorMessage) {
      onReady?.(Boolean(hasScene || notice));
      return;
    }
    if (
      hasScene &&
      (sceneReadinessRef.current?.roomData !== roomData ||
        !sceneReadinessRef.current.rendered)
    ) {
      return;
    }
    onReady?.(Boolean(hasScene || notice));
  }, [errorMessage, loading, notice, onReady, roomData, sceneRenderVersion]);

  useLayoutEffect(() => {
    resizeSceneRef.current();
  }, [screenRenderContext?.fitScale]);

  const legendItems = useMemo(() => {
    if (!roomData?.racks.length) {
      return [];
    }

    const uniqueTypes = new Map<string, string>();
    roomData.racks.forEach((rack) => {
      const label = rack.rack_type_name?.trim();
      if (!label) {
        return;
      }
      const key = `${rack.rack_type || "type"}:${label}`;
      if (!uniqueTypes.has(key)) {
        uniqueTypes.set(key, label);
      }
    });
    return Array.from(uniqueTypes.entries()).map(([key, label]) => ({
      key,
      label,
    }));
  }, [roomData?.racks]);

  const selectedRackPosition = selectedRack
    ? getRoom3DPositionLabel(selectedRack)
    : "";
  const selectedConflictRacks = selectedRack?.is_conflict
    ? (selectedRack.conflict_racks ?? [])
    : [];
  const shouldShowHoverTooltip = Boolean(
    hoverState && !selectedDevice,
  );
  const shouldShowRackPanel = Boolean(
    selectedRack?.is_conflict && !selectedDevice,
  );
  const hoverRackFields = useMemo(() => {
    const rack = hoverState?.rack;
    if (!rack) {
      return [];
    }

    const fields: Array<{ label: string; value: React.ReactNode }> = [
      {
        label: t("dashboard.room3DLocation"),
        value: getRoom3DPositionLabel(rack),
      },
      {
        label: t("dashboard.room3DUCount"),
        value: rack.u_count ?? "-",
      },
      {
        label: t("dashboard.room3DUsedU"),
        value: rack.used_u ?? "-",
      },
      {
        label: t("dashboard.room3DFreeU"),
        value: rack.free_u ?? "-",
      },
      {
        label: t("dashboard.room3DDeviceCount"),
        value: rack.device_count ?? getRoom3DRackDevices(rack).length,
      },
    ];
    if (rack.is_conflict) {
      fields.push({
        label: t("dashboard.room3DConflictRacks"),
        value: `${rack.conflict_racks?.length ?? 0}${t("dashboard.room3DCountUnit")}`,
      });
    } else if (rack.unplaced_device_count) {
      fields.push({
        label: t("dashboard.room3DUnplaced"),
        value: rack.unplaced_device_count,
      });
    }
    const alarmSummary = aggregateRackAlarmSummary(getRoom3DRackDevices(rack));
    if (alarmSummary.count > 0) {
      fields.push({
        label: t("dashboard.room3DActiveAlarms"),
        value: `${alarmSummary.count}${t("dashboard.room3DCountUnit")}`,
      });
      if (alarmSummary.highest_severity) {
        fields.push({
          label: t("dashboard.room3DHighestSeverity"),
          value: formatRoom3DSeverityLabel(alarmSummary.highest_severity, t),
        });
      }
    }
    return fields;
  }, [hoverState?.rack, t]);
  useLayoutEffect(() => {
    if (!shouldShowHoverTooltip) {
      return undefined;
    }

    const tooltipNode = tooltipRef.current;
    if (!tooltipNode) {
      return undefined;
    }

    const updateTooltipSize = () => {
      setTooltipSize((previous) =>
        previous.width === tooltipNode.offsetWidth &&
        previous.height === tooltipNode.offsetHeight
          ? previous
          : {
            width: tooltipNode.offsetWidth,
            height: tooltipNode.offsetHeight,
          },
      );
    };

    updateTooltipSize();
    const resizeObserver = new ResizeObserver(updateTooltipSize);
    resizeObserver.observe(tooltipNode);
    window.addEventListener("resize", updateTooltipSize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateTooltipSize);
    };
  }, [hoverRackFields, shouldShowHoverTooltip]);
  const hoverTooltipStyle = useMemo<React.CSSProperties | undefined>(() => {
    if (!hoverState) {
      return undefined;
    }

    const scale = readableOverlayScale;
    const offset = 6 * scale;
    const margin = 8 * scale;
    const fallbackWidth = 184 * scale;
    const fallbackHeight = 132 * scale;
    const width = tooltipSize.width || fallbackWidth;
    const height = tooltipSize.height || fallbackHeight;
    const roomNode = roomRef.current;
    const roomRect = roomNode?.getBoundingClientRect();
    const scaleX =
      roomNode && roomRect?.width ? roomNode.offsetWidth / roomRect.width : 1;
    const scaleY =
      roomNode && roomRect?.height ? roomNode.offsetHeight / roomRect.height : 1;
    const localX = roomRect
      ? (hoverState.x - roomRect.left) * scaleX
      : hoverState.x;
    const localY = roomRect
      ? (hoverState.y - roomRect.top) * scaleY
      : hoverState.y;
    const roomWidth = roomNode?.offsetWidth || window.innerWidth;
    const roomHeight = roomNode?.offsetHeight || window.innerHeight;
    const minLeft = margin;
    const maxLeft = Math.max(minLeft, roomWidth - width - margin);
    const minTop = margin;
    const maxTop = Math.max(minTop, roomHeight - height - margin);
    const preferredLeft = localX + offset;
    const flippedLeft = localX - width - offset;
    const preferredTop = localY + offset;

    return {
      left: Math.min(
        Math.max(
          preferredLeft + width > roomWidth - margin
            ? flippedLeft
            : preferredLeft,
          minLeft,
        ),
        maxLeft,
      ),
      top: Math.min(Math.max(preferredTop, minTop), maxTop),
    };
  }, [hoverState, readableOverlayScale, tooltipSize]);
  const selectedDeviceFields = useMemo(() => {
    if (!selectedDevice) {
      return [];
    }

    const fields: Array<{ label: string; value: React.ReactNode }> = [
      {
        label: t("dashboard.room3DDeviceName"),
        value: selectedDevice.device.device_name,
      },
      {
        label: t("dashboard.room3DDeviceRack"),
        value: selectedDevice.rack.rack_name,
      },
    ];
    if (selectedDevice.device.model_id) {
      fields.push({
        label: t("dashboard.room3DDeviceModel"),
        value: selectedDevice.device.model_id,
      });
    }
    if (selectedDevice.device.rack_u_start) {
      fields.push({
        label: t("dashboard.room3DDeviceUPosition"),
        value: `U${selectedDevice.device.rack_u_start}`,
      });
    }
    if (selectedDevice.device.u_size) {
      fields.push({
        label: t("dashboard.room3DDeviceHeight"),
        value: `${selectedDevice.device.u_size}U`,
      });
    }
    if (selectedDevice.device.status) {
      fields.push({
        label: t("dashboard.room3DDeviceStatus"),
        value: selectedDevice.device.status,
      });
    }
    fields.push({
      label: t("dashboard.room3DActiveAlarms"),
      value: formatRoom3DDeviceAlarmCountValue(selectedDevice.device, t),
    });
    if (shouldShowRoom3DDeviceHighestSeverity(selectedDevice.device)) {
      fields.push({
        label: t("dashboard.room3DHighestSeverity"),
        value: formatRoom3DSeverityLabel(
          selectedDevice.device.highest_severity,
          t,
        ),
      });
    }
    return fields;
  }, [selectedDevice, t]);

  const showRoomSwitcher = !injected && !editMode && rooms.length > 0;
  const switcherSelection = resolveRoom3DSelection({
    rooms,
    savedRoomId,
    runtimeRoomId,
  });
  const switcherValue =
    switcherSelection.status === "ready" ? switcherSelection.roomId : undefined;
  const roomSwitcher = showRoomSwitcher ? (
    <Select
      value={switcherValue}
      options={rooms.map((item) => ({ value: item.id, label: item.name }))}
      onChange={(value) => setRuntimeRoomId(value)}
      placeholder={t("dashboard.room3DSwitchPlaceholder")}
      popupMatchSelectWidth={false}
    />
  ) : null;

  if (!allowedOnSurface) {
    return (
      <div className={styles.stateBox}>
        <Empty description={t("dashboard.room3DLoadFailed")} />
      </div>
    );
  }

  if (loading) {
    return (
      <div className={`${styles.stateBox} ${styles.stateBoxWithControl}`}>
        {roomSwitcher && (
          <div className={styles.roomSwitch}>{roomSwitcher}</div>
        )}
        <Spin />
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className={`${styles.stateBox} ${styles.stateBoxWithControl}`}>
        {roomSwitcher && (
          <div className={styles.roomSwitch}>{roomSwitcher}</div>
        )}
        <Alert type="error" showIcon message={errorMessage} />
      </div>
    );
  }

  if (!validation.ok) {
    return (
      <div className={`${styles.stateBox} ${styles.stateBoxWithControl}`}>
        {roomSwitcher && (
          <div className={styles.roomSwitch}>{roomSwitcher}</div>
        )}
        <Alert
          type="error"
          showIcon
          message={t("dashboard.room3DFormatError")}
          description={validationError}
        />
      </div>
    );
  }

  if (!roomData.racks.length) {
    return (
      <div className={`${styles.stateBox} ${styles.stateBoxWithControl}`}>
        {roomSwitcher && (
          <div className={styles.roomSwitch}>{roomSwitcher}</div>
        )}
        <div className={styles.stateContent}>
          {visibleNotice && (
            <Alert
              type="warning"
              showIcon
              closable={{
                closeIcon: true,
                "aria-label": t("dashboard.room3DDismissNotice"),
              }}
              message={visibleNotice}
              onClose={() => setDismissedNotice(visibleNotice)}
            />
          )}
          <Empty description={t("dashboard.room3DNoData")} />
        </div>
      </div>
    );
  }

  const showRoomSummary = !showRoomSwitcher;
  const roomRackCount = roomData.racks.length;
  const roomSummaryText = `${t("dashboard.room3DRoomNameLabel")}${roomData.room.name}${t("dashboard.room3DRackCountPrefix")}${roomRackCount}${t("dashboard.room3DRackCountSuffix")}`;

  return (
    <div
      ref={roomRef}
      className={[
        styles.room3D,
        displayOptions.immersive ? styles.room3DImmersive : "",
        chromeVisible ? styles.room3DChromeVisible : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onPointerEnter={() => setChromeVisible(true)}
      onPointerLeave={() => setChromeVisible(false)}
      style={{
        "--room3d-readable-scale": readableOverlayScale,
      } as React.CSSProperties}
    >
      <div ref={mountRef} className={styles.canvas} />
      {roomSwitcher && (
        <div className={styles.roomSwitchOverlay}>{roomSwitcher}</div>
      )}
      <div className={styles.topBar}>
        {showRoomSummary && (
          <div className={styles.roomTitle} title={roomSummaryText}>
            <span className={styles.roomTitleLabel}>
              {t("dashboard.room3DRoomNameLabel")}
            </span>
            <strong className={styles.roomTitleName}>{roomData.room.name}</strong>
            <span className={styles.roomTitleCount}>
              {t("dashboard.room3DRackCountPrefix")}
              {roomRackCount}
              {t("dashboard.room3DRackCountSuffix")}
            </span>
          </div>
        )}
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={() => resetViewRef.current()}
          title={t("dashboard.room3DResetView")}
        />
      </div>
      {visibleNotice && (
        <div className={styles.noticePanel}>
          <Alert
            type="warning"
            showIcon
            closable={{
              closeIcon: true,
              "aria-label": t("dashboard.room3DDismissNotice"),
            }}
            message={visibleNotice}
            onClose={() => setDismissedNotice(visibleNotice)}
          />
        </div>
      )}
      {!isCompact && (
        <div className={styles.legend}>
          {legendItems.map((item) => (
            <span key={item.key} className={styles.legendItem}>
              {item.label}
            </span>
          ))}
        </div>
      )}
      {shouldShowHoverTooltip && hoverState && (
        <div
          ref={tooltipRef}
          className={styles.tooltip}
          style={hoverTooltipStyle}
        >
          <strong className={styles.tooltipTitle}>
            {hoverState.rack.is_conflict
              ? t("dashboard.room3DPositionConflict")
              : hoverState.rack.rack_name}
          </strong>
          <div className={styles.tooltipGrid}>
            {hoverRackFields.map((field) => (
              <React.Fragment key={field.label}>
                <span>{field.label}</span>
                <strong>{field.value}</strong>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
      {shouldShowRackPanel &&
        selectedRack && (
          <div className={`${styles.infoPanel} ${styles.conflictPanel}`}>
            <div className={styles.infoTitle}>
              {t("dashboard.room3DPositionConflict")}
            </div>
            <div className={styles.infoGrid}>
              <span>{t("dashboard.room3DLocation")}</span>
              <strong>{selectedRackPosition}</strong>
              <span>{t("dashboard.room3DConflictRacks")}</span>
              <strong>
                {selectedConflictRacks.length}
                {t("dashboard.room3DCountUnit")}
              </strong>
            </div>
            <div className={styles.conflictRackList}>
              {selectedConflictRacks.map((rack) => (
                <div key={rack.rack_id}>
                  <strong>{rack.rack_name}</strong>
                  <span>
                    {t("dashboard.room3DLocationLabel")}
                    {getRoom3DPositionLabel(rack)}
                  </span>
                </div>
              ))}
            </div>
          </div>
      )}
      {selectedDevice && (
        <div className={styles.devicePanel}>
          <div className={styles.devicePanelHeader}>
            <span>{t("dashboard.room3DDeviceDetail")}</span>
          </div>
          <div className={styles.deviceGrid}>
            {selectedDeviceFields.map((field) => (
              <React.Fragment key={field.label}>
                <span>{field.label}</span>
                <strong>{field.value}</strong>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default Room3D;
