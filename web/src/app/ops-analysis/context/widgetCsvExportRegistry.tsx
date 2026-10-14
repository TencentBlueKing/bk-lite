'use client';

import React, { createContext, useContext, useEffect, useMemo, useRef } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { downloadCsvFile } from '@/app/ops-analysis/utils/csvDocument';
import {
  buildWidgetCsvLabels,
  createWidgetCsvExport,
  describeWidgetCsvExportNotice,
  supportsWidgetCsvExport,
  type WidgetCsvExportRuntime,
} from '@/app/ops-analysis/utils/widgetCsvExport';

export interface WidgetCsvExportRequest {
  title: string;
}

export type WidgetCsvExporter = (request: WidgetCsvExportRequest) => Promise<void>;

export interface WidgetCsvExportRegistry {
  register: (widgetId: string, exporter: WidgetCsvExporter) => () => void;
  run: (widgetId: string, request: WidgetCsvExportRequest) => Promise<boolean>;
  publishWidgetRawData: (widgetId: string, rawData: unknown) => void;
  readWidgetRawData: (widgetId: string) => unknown;
}

const WidgetCsvExportRegistryContext = createContext<WidgetCsvExportRegistry | null>(null);

export const useWidgetCsvExportRegistryState = (): WidgetCsvExportRegistry => {
  const exportersRef = useRef(new Map<string, WidgetCsvExporter>());
  const rawDataRef = useRef(new Map<string, unknown>());
  return useMemo<WidgetCsvExportRegistry>(() => ({
    register: (widgetId, exporter) => {
      exportersRef.current.set(widgetId, exporter);
      return () => {
        if (exportersRef.current.get(widgetId) === exporter) {
          exportersRef.current.delete(widgetId);
        }
      };
    },
    run: async (widgetId, request) => {
      const exporter = exportersRef.current.get(widgetId);
      if (!exporter) return false;
      await exporter(request);
      return true;
    },
    publishWidgetRawData: (widgetId, rawData) => {
      if (rawData === undefined) {
        rawDataRef.current.delete(widgetId);
        return;
      }
      rawDataRef.current.set(widgetId, rawData);
    },
    readWidgetRawData: (widgetId) => rawDataRef.current.get(widgetId),
  }), []);
};

export const WidgetCsvExportRegistryProvider: React.FC<{
  children: React.ReactNode;
  registry?: WidgetCsvExportRegistry;
}> = ({ children, registry }) => {
  const owned = useWidgetCsvExportRegistryState();
  return (
    <WidgetCsvExportRegistryContext.Provider value={registry ?? owned}>
      {children}
    </WidgetCsvExportRegistryContext.Provider>
  );
};

export const useWidgetCsvExportRegistry = () => useContext(WidgetCsvExportRegistryContext);

export const notifyWidgetCsvExportNotStarted = (
  started: boolean,
  t: (id: string) => string,
) => {
  if (!started) message.warning(t('dashboard.csvExportPending'));
};

export const deliverWidgetCsvExport = async (
  runtime: WidgetCsvExportRuntime,
  request: WidgetCsvExportRequest,
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string,
  readLatest?: () => WidgetCsvExportRuntime,
) => {
  const outcome = await createWidgetCsvExport(
    runtime,
    request,
    buildWidgetCsvLabels((id) => t(id)),
    undefined,
    readLatest ? { readLatest } : undefined,
  );
  if (outcome.kind === 'downloaded' || outcome.kind === 'truncated') {
    downloadCsvFile(outcome.filename, outcome.csv);
  }
  const notice = describeWidgetCsvExportNotice(outcome, t);
  if (!notice) return;
  if (notice.level === 'info') message.info(notice.text);
  else if (notice.level === 'warning') message.warning(notice.text);
  else message.error(notice.text);
};

export const useRegisterWidgetCsvExport = (
  widgetId: string,
  surface: string | undefined,
  chartType: string | undefined,
  getRuntime: () => WidgetCsvExportRuntime,
) => {
  const registry = useWidgetCsvExportRegistry();
  const { t } = useTranslation();
  const getRuntimeRef = useRef(getRuntime);
  getRuntimeRef.current = getRuntime;
  const tRef = useRef(t);
  tRef.current = t;

  useEffect(() => {
    if (!registry) return undefined;
    if (surface !== 'dashboard' && surface !== 'screen' && surface !== 'report') return undefined;
    if (!supportsWidgetCsvExport(chartType)) return undefined;
    return registry.register(widgetId, (request) => (
      deliverWidgetCsvExport(
        getRuntimeRef.current(),
        request,
        tRef.current,
        () => getRuntimeRef.current(),
      )
    ));
  }, [chartType, registry, surface, widgetId]);
};
