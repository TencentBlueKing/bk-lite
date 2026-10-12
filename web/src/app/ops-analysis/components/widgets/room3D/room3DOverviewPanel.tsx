"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "antd";
import { LeftOutlined, RightOutlined } from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import type { Room3DRack } from "./room3DData";
import {
  ROOM3D_OVERVIEW_MOTION_MS,
  easeRoom3DOverview,
  formatRoom3DOverviewCount,
  formatRoom3DOverviewPercent,
  room3DOverviewCoverage,
  summarizeRoom3DOverview,
} from "./room3DOverview";
import styles from "./room3D.module.scss";

const USAGE_RING_RADIUS = 22;
const USAGE_RING_CIRCUMFERENCE = 2 * Math.PI * USAGE_RING_RADIUS;

interface Room3DOverviewPanelProps {
  racks: readonly Room3DRack[];
  expanded: boolean;
  onToggle: () => void;
}

const useAnimatedMetric = (value: number | null) => {
  const [shown, setShown] = useState(value);
  const shownRef = useRef(value);

  useEffect(() => {
    const from = shownRef.current;
    if (
      value === null ||
      from === null ||
      from === value ||
      !Number.isFinite(from) ||
      !Number.isFinite(value)
    ) {
      shownRef.current = value;
      setShown(value);
      return undefined;
    }

    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / ROOM3D_OVERVIEW_MOTION_MS);
      const next =
        progress >= 1
          ? value
          : from + (value - from) * easeRoom3DOverview(progress);
      shownRef.current = next;
      setShown(next);
      if (progress < 1) {
        frame = window.requestAnimationFrame(tick);
      }
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [value]);

  return shown;
};

const Room3DOverviewPanel: React.FC<Room3DOverviewPanelProps> = ({
  racks,
  expanded,
  onToggle,
}) => {
  const { t } = useTranslation();
  const stats = useMemo(() => summarizeRoom3DOverview(racks), [racks]);
  const rackCount = useAnimatedMetric(stats.rackCount);
  const deviceCount = useAnimatedMetric(stats.deviceCount);
  const usedU = useAnimatedMetric(stats.usedU);
  const totalU = useAnimatedMetric(stats.totalU);
  const freeU = useAnimatedMetric(stats.freeU);
  const usageRatio = useAnimatedMetric(stats.usageRatio);
  const monitoredCount = useAnimatedMetric(stats.monitoredCount);
  const alarmDeviceCount = useAnimatedMetric(stats.alarmDeviceCount);
  const coverage = room3DOverviewCoverage(monitoredCount, deviceCount);
  const usageRingRatio =
    usageRatio === null || !Number.isFinite(usageRatio)
      ? null
      : Math.min(1, Math.max(0, usageRatio));
  const usageDashOffset =
    usageRingRatio === null
      ? USAGE_RING_CIRCUMFERENCE
      : USAGE_RING_CIRCUMFERENCE * (1 - usageRingRatio);
  const coverageWidth =
    coverage === null || !Number.isFinite(coverage)
      ? 0
      : `${Math.min(100, Math.max(0, coverage * 100))}%`;
  const alarmActive =
    alarmDeviceCount !== null &&
    Number.isFinite(alarmDeviceCount) &&
    alarmDeviceCount > 0;
  const showCollapsedAlarm =
    alarmDeviceCount !== null &&
    Number.isFinite(alarmDeviceCount) &&
    Math.round(alarmDeviceCount) > 0;

  return (
    <div
      className={[
        styles.overviewShell,
        expanded ? "" : styles.overviewShellCollapsed,
      ]
        .filter(Boolean)
        .join(" ")}
      data-expanded={expanded ? "true" : "false"}
    >
      <section
        className={styles.overviewExpanded}
        aria-hidden={expanded ? undefined : true}
        inert={expanded ? undefined : true}
      >
        <div className={styles.overviewHeader}>
          <div className={styles.overviewTitle}>
            {t("dashboard.room3DOverviewTitle")}
          </div>
          <Button
            size="small"
            type="text"
            icon={<LeftOutlined />}
            aria-expanded={expanded}
            aria-label={t("dashboard.room3DOverviewCollapse")}
            tabIndex={expanded ? 0 : -1}
            onClick={onToggle}
          />
        </div>
        <article className={styles.overviewCard}>
          <div className={styles.overviewCardTitle}>
            {t("dashboard.room3DOverviewAsset")}
          </div>
          <div className={styles.assetMetrics}>
            <div className={styles.assetMetric}>
              <span>{t("dashboard.room3DOverviewRacks")}</span>
              <strong>{formatRoom3DOverviewCount(rackCount)}</strong>
            </div>
            <i className={styles.assetDivider} />
            <div className={styles.assetMetric}>
              <span>{t("dashboard.room3DOverviewDevices")}</span>
              <strong>{formatRoom3DOverviewCount(deviceCount)}</strong>
            </div>
          </div>
        </article>
        <article className={styles.overviewCard}>
          <div className={styles.overviewCardTitle}>
            {t("dashboard.room3DOverviewCapacity")}
          </div>
          <div className={styles.capacityBody}>
            <div className={styles.usageRingWrap}>
              <svg
                className={styles.usageRing}
                viewBox="0 0 64 64"
                aria-hidden
              >
                <circle
                  cx="32"
                  cy="32"
                  r={USAGE_RING_RADIUS}
                  className={styles.usageRingTrack}
                />
                <circle
                  cx="32"
                  cy="32"
                  r={USAGE_RING_RADIUS}
                  className={styles.usageRingValue}
                  strokeDasharray={`${USAGE_RING_CIRCUMFERENCE} ${USAGE_RING_CIRCUMFERENCE}`}
                  strokeDashoffset={usageDashOffset}
                />
              </svg>
              <strong className={styles.usagePercent}>
                {formatRoom3DOverviewPercent(usageRatio)}
              </strong>
            </div>
            <div className={styles.capacityText}>
              <span>
                {t("dashboard.room3DOverviewUsedTotal", undefined, {
                  used: formatRoom3DOverviewCount(usedU),
                  total: formatRoom3DOverviewCount(totalU),
                })}
              </span>
              <span>
                {t("dashboard.room3DOverviewFree", undefined, {
                  free: formatRoom3DOverviewCount(freeU),
                })}
              </span>
            </div>
          </div>
        </article>
        <article className={styles.overviewCard}>
          <div className={styles.overviewCardTitle}>
            {t("dashboard.room3DOverviewMonitoring")}
          </div>
          <div className={styles.monitorLine}>
            {t("dashboard.room3DOverviewMonitored", undefined, {
              monitored: formatRoom3DOverviewCount(monitoredCount),
              total: formatRoom3DOverviewCount(deviceCount),
            })}
          </div>
          <div className={styles.coverageTrack}>
            <i className={styles.coverageFill} style={{ width: coverageWidth }} />
          </div>
          <div
            className={[
              styles.alarmLine,
              alarmActive ? styles.alarmLineActive : styles.alarmLineIdle,
            ].join(" ")}
          >
            <span className={styles.alarmLabel}>
              <i className={styles.alarmDot} />
              {t("dashboard.room3DOverviewAlarmDevices")}
            </span>
            <strong>{formatRoom3DOverviewCount(alarmDeviceCount)}</strong>
          </div>
        </article>
      </section>
      <button
        type="button"
        className={styles.overviewCollapsed}
        aria-expanded={expanded}
        aria-label={t("dashboard.room3DOverviewExpand")}
        aria-hidden={expanded ? true : undefined}
        inert={expanded ? true : undefined}
        tabIndex={expanded ? -1 : 0}
        onClick={onToggle}
      >
        <span className={styles.overviewCollapsedTitle}>
          {t("dashboard.room3DOverviewTitle")}
        </span>
        {showCollapsedAlarm && (
          <span className={styles.overviewCollapsedAlarm}>
            <i className={styles.alarmDot} />
            <strong>{formatRoom3DOverviewCount(alarmDeviceCount)}</strong>
          </span>
        )}
        <RightOutlined className={styles.overviewCollapsedArrow} />
      </button>
    </div>
  );
};

export default Room3DOverviewPanel;
