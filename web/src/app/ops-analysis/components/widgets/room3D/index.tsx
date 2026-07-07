"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Empty, Spin } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import type {
  ScreenRenderContext,
  ValueConfig,
} from "@/app/ops-analysis/types/dashBoard";
import {
  getRoom3DDisplayOptions,
  getRoom3DPositionLabel,
  getRoom3DRackDevices,
  type Room3DRenderableDevice,
  type Room3DRack,
  validateRoom3DData,
} from "./room3DData";
import { getRackVisualMeta } from "./room3DMeshes";
import { createRoom3DScene } from "./room3DScene";
import styles from "./room3D.module.scss";

interface Room3DProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready: boolean) => void;
}

interface PointerState {
  rack: Room3DRack;
  x: number;
  y: number;
}

const Room3D: React.FC<Room3DProps> = ({
  rawData,
  loading = false,
  config,
  screenRenderContext,
  onReady,
}) => {
  const { t } = useTranslation();
  const mountRef = useRef<HTMLDivElement | null>(null);
  const resetViewRef = useRef<() => void>(() => undefined);
  const validation = useMemo(
    () => validateRoom3DData(rawData, t),
    [rawData, t],
  );
  const displayOptions = useMemo(
    () => getRoom3DDisplayOptions(config),
    [config],
  );
  const roomData = validation.ok ? validation.data : null;
  const validationError = "error" in validation ? validation.error : "";
  const notice = roomData?.notice;
  const [hoverState, setHoverState] = useState<PointerState | null>(null);
  const [selectedRack, setSelectedRack] = useState<Room3DRack | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<{
    rack: Room3DRack;
    device: Room3DRenderableDevice;
  } | null>(null);
  const [chromeVisible, setChromeVisible] = useState(false);

  const isCompact = (screenRenderContext?.widgetDensity || 0) > 0.5;

  useEffect(() => {
    if (!loading) {
      onReady?.(Boolean(roomData?.racks.length || notice));
    }
  }, [loading, notice, onReady, roomData?.racks.length]);

  useEffect(() => {
    setHoverState(null);
    setSelectedRack(null);
    setSelectedDevice(null);
  }, [rawData]);

  useEffect(() => {
    const mountNode = mountRef.current;
    if (!mountNode || !roomData?.racks.length) {
      resetViewRef.current = () => undefined;
      return undefined;
    }

    const controller = createRoom3DScene(
      mountNode,
      roomData,
      { transparentScene: displayOptions.transparentScene },
      {
        onHover: setHoverState,
        onSelect: (rack) => {
          setSelectedRack(rack);
          if (!rack) {
            setSelectedDevice(null);
          }
        },
        onDeviceSelect: setSelectedDevice,
      },
    );
    resetViewRef.current = controller.resetView;

    return () => {
      controller.dispose();
      resetViewRef.current = () => undefined;
    };
  }, [displayOptions.transparentScene, roomData]);

  const legendItems = useMemo(() => {
    if (!roomData?.racks.length) {
      return [];
    }

    const uniqueTypes = new Map<string, ReturnType<typeof getRackVisualMeta>>();
    roomData.racks.forEach((rack) => {
      const key = String(rack.rack_type || "default");
      if (!uniqueTypes.has(key)) {
        uniqueTypes.set(key, getRackVisualMeta(rack.rack_type));
      }
    });
    return Array.from(uniqueTypes.entries()).map(([key, meta]) => ({
      key,
      ...meta,
    }));
  }, [roomData?.racks]);

  const selectedRackDevices = useMemo(
    () => (selectedRack ? getRoom3DRackDevices(selectedRack) : []),
    [selectedRack],
  );
  const selectedRackPosition = selectedRack
    ? getRoom3DPositionLabel(selectedRack)
    : "";
  const selectedConflictRacks = selectedRack?.is_conflict
    ? (selectedRack.conflict_racks ?? [])
    : [];
  const shouldShowHoverTooltip = Boolean(
    hoverState && !selectedRack && !selectedDevice,
  );
  const shouldShowRackPanel = Boolean(selectedRack && !selectedDevice);
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
    return fields;
  }, [selectedDevice, t]);

  if (loading) {
    return (
      <div className={styles.stateBox}>
        <Spin />
      </div>
    );
  }

  if (!validation.ok) {
    return (
      <div className={styles.stateBox}>
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
      <div className={styles.stateBox}>
        <div className={styles.stateContent}>
          {notice && <Alert type="warning" showIcon message={notice} />}
          <Empty description={t("dashboard.room3DNoData")} />
        </div>
      </div>
    );
  }

  const roomRackCount = roomData.racks.length;
  const roomSummaryText = `${t("dashboard.room3DRoomNameLabel")}${roomData.room.name}${t("dashboard.room3DRackCountPrefix")}${roomRackCount}${t("dashboard.room3DRackCountSuffix")}`;

  return (
    <div
      className={[
        styles.room3D,
        displayOptions.immersive ? styles.room3DImmersive : "",
        chromeVisible ? styles.room3DChromeVisible : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onPointerEnter={() => setChromeVisible(true)}
      onPointerLeave={() => setChromeVisible(false)}
    >
      <div ref={mountRef} className={styles.canvas} />
      <div className={styles.topBar}>
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
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={() => resetViewRef.current()}
          title={t("dashboard.room3DResetView")}
        />
      </div>
      {notice && (
        <div className={styles.noticePanel}>
          <strong>{notice}</strong>
        </div>
      )}
      {!isCompact && (
        <div className={styles.legend}>
          {legendItems.map((item) => (
            <span key={item.key} className={styles.legendItem}>
              <i style={{ backgroundColor: item.color }} />
              {t(item.labelKey)}
            </span>
          ))}
        </div>
      )}
      {shouldShowHoverTooltip && hoverState && (
        <div
          className={styles.tooltip}
          style={{
            left: hoverState.x + 12,
            top: hoverState.y + 12,
          }}
        >
          <strong>
            {hoverState.rack.is_conflict
              ? t("dashboard.room3DPositionConflict")
              : hoverState.rack.rack_name}
          </strong>
          <span>
            {t("dashboard.room3DLocationLabel")}
            {getRoom3DPositionLabel(hoverState.rack)}
          </span>
          {hoverState.rack.is_conflict && (
            <span>
              {t("dashboard.room3DConflictRacksLabel")}
              {hoverState.rack.conflict_racks?.length ?? 0}
              {t("dashboard.room3DCountUnit")}
            </span>
          )}
        </div>
      )}
      {shouldShowRackPanel &&
        selectedRack &&
        (selectedRack.is_conflict ? (
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
        ) : (
          <div className={styles.infoPanel}>
            <div className={styles.infoTitle}>{selectedRack.rack_name}</div>
            <div className={styles.infoGrid}>
              <span>{t("dashboard.room3DLocation")}</span>
              <strong>{selectedRackPosition}</strong>
              <span>{t("dashboard.room3DUCount")}</span>
              <strong>{selectedRack.u_count ?? "-"}</strong>
              <span>{t("dashboard.room3DUsedU")}</span>
              <strong>{selectedRack.used_u ?? "-"}</strong>
              <span>{t("dashboard.room3DFreeU")}</span>
              <strong>{selectedRack.free_u ?? "-"}</strong>
              <span>{t("dashboard.room3DDeviceCount")}</span>
              <strong>
                {selectedRack.device_count ??
                  (selectedRackDevices.length || "-")}
              </strong>
              {Boolean(selectedRack.unplaced_device_count) && (
                <>
                  <span>{t("dashboard.room3DUnplaced")}</span>
                  <strong>{selectedRack.unplaced_device_count}</strong>
                </>
              )}
            </div>
          </div>
        ))}
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
