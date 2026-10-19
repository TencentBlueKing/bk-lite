'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useCallback
} from 'react';
import {
  Input,
  Button,
  Select,
  message,
  Spin,
  Tag,
  Popover,
  Tooltip
} from 'antd';
import { PlusOutlined, CloseOutlined, HolderOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import CompactEmptyState from '@/components/compact-empty-state';
import { ModalRef, ModalConfig } from '@/app/monitor/types';
import {
  MonitorObjectItem,
  DisplayColumn,
  PluginOption,
  MetricOption
} from './types';
import { useTranslation } from '@/utils/i18n';
import useObjectApi from './api';
import { invalidateMonitorObjectsCache } from '@/app/monitor/utils/monitorObjectCache';

interface DisplayFieldsModalProps {
  onSuccess?: () => void;
}

interface ConfigObjectNode {
  id: number;
  name: string;
  display_name: string;
  isBase: boolean;
}

const DisplayFieldsModal = forwardRef<ModalRef, DisplayFieldsModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const {
      getObjectDetail,
      getObjectChildrenRaw,
      getObjectPlugins,
      getObjectMetrics,
      getMetricVmFields,
      saveDisplayFields
    } = useObjectApi();

    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [confirmLoading, setConfirmLoading] = useState(false);
    const [title, setTitle] = useState('');
    const [nodes, setNodes] = useState<ConfigObjectNode[]>([]);
    const [activeId, setActiveId] = useState<number | null>(null);
    const [columnsMap, setColumnsMap] = useState<Record<number, DisplayColumn[]>>({});
    const dirtyRef = useRef<Set<number>>(new Set());
    const [pluginsMap, setPluginsMap] = useState<Record<number, PluginOption[]>>({});
    const [metricsMap, setMetricsMap] = useState<Record<string, MetricOption[]>>({});
    const [metricSearchOptionsMap, setMetricSearchOptionsMap] = useState<
      Record<string, MetricOption[]>
    >({});
    const [selectedMetricOptionsMap, setSelectedMetricOptionsMap] = useState<
      Record<string, MetricOption>
    >({});
    const [fieldPicker, setFieldPicker] = useState<{
      visible: boolean;
      loading: boolean;
      fields: string[];
      colIdx: number;
      bindIdx: number;
    }>({
      visible: false,
      loading: false,
      fields: [],
      colIdx: -1,
      bindIdx: -1
    });
    const dragIndexRef = useRef<number | null>(null);
    const columnsMapRef = useRef<Record<number, DisplayColumn[]>>({});
    const activeIdRef = useRef<number | null>(null);
    // 镜像 pluginsMap，供 loadNodeOptions 同步读取已加载状态（避免在 setState updater 内做副作用）
    const pluginsMapRef = useRef<Record<number, PluginOption[]>>({});
    // 正在请求中的指标 key，避免预热与下拉懒加载并发重复请求同一插件
    const inflightMetricsRef = useRef<Set<string>>(new Set());
    const sessionAbortRef = useRef<AbortController | null>(null);
    const metricSearchTimerRef = useRef<Record<string, ReturnType<typeof setTimeout>>>(
      {}
    );
    const metricSearchGenerationRef = useRef<Record<string, number>>({});

    const abortSession = () => {
      sessionAbortRef.current?.abort();
      sessionAbortRef.current = null;
      Object.values(metricSearchTimerRef.current).forEach((timer) => clearTimeout(timer));
      metricSearchTimerRef.current = {};
      inflightMetricsRef.current = new Set();
    };

    useEffect(() => () => {
      abortSession();
    }, []);

    useEffect(() => {
      pluginsMapRef.current = pluginsMap;
    }, [pluginsMap]);

    useEffect(() => {
      columnsMapRef.current = columnsMap;
    }, [columnsMap]);

    useEffect(() => {
      activeIdRef.current = activeId;
    }, [activeId]);

    const loadNodeOptions = useCallback(
      async (node: ConfigObjectNode, signal?: AbortSignal) => {
        if (pluginsMapRef.current[node.id]) return;
        try {
          const plugins = await getObjectPlugins(node.id, signal);
          if (signal?.aborted) return;
          setPluginsMap((p) => ({ ...p, [node.id]: plugins || [] }));
        } catch (error: unknown) {
          if ((error as { name?: string } | null)?.name === 'AbortError' || signal?.aborted) {
            return;
          }
          message.error(t('common.operationFailed'));
        }
      },
      [getObjectPlugins, t]
    );

    useImperativeHandle(ref, () => ({
      showModal: async ({ form }: ModalConfig) => {
        const obj = form as MonitorObjectItem;
        abortSession();
        const sessionAbort = new AbortController();
        sessionAbortRef.current = sessionAbort;
        setVisible(true);
        setLoading(true);
        dirtyRef.current = new Set();
        pluginsMapRef.current = {};
        inflightMetricsRef.current = new Set();
        setColumnsMap({});
        setPluginsMap({});
        setMetricsMap({});
        setMetricSearchOptionsMap({});
        setSelectedMetricOptionsMap({});
        setFieldPicker({
          visible: false,
          loading: false,
          fields: [],
          colIdx: -1,
          bindIdx: -1
        });
        setTitle(
          `${t('monitor.object.displayFieldsConfig')} - ${obj.display_name || obj.name}`
        );
        try {
          const baseDetail = await getObjectDetail(obj.id, sessionAbort.signal);
          const baseNode: ConfigObjectNode = {
            id: obj.id,
            name: baseDetail.name,
            display_name: baseDetail.display_name || baseDetail.name,
            isBase: true
          };
          const initColumns: Record<number, DisplayColumn[]> = {
            [obj.id]: (baseDetail.display_fields || []).map((c) => ({ ...c }))
          };
          const allNodes: ConfigObjectNode[] = [baseNode];
          if ((obj.children_count ?? 0) > 0) {
            const children = await getObjectChildrenRaw(obj.id, sessionAbort.signal);
            for (const child of children) {
              allNodes.push({
                id: child.id,
                name: child.name,
                display_name: child.display_name || child.name,
                isBase: false
              });
              initColumns[child.id] = (child.display_fields || []).map(
                (c) => ({ ...c })
              );
            }
          }
          setNodes(allNodes);
          columnsMapRef.current = initColumns;
          setColumnsMap(initColumns);
          activeIdRef.current = obj.id;
          setActiveId(obj.id);
          await loadNodeOptions(baseNode, sessionAbort.signal);
        } catch (error: unknown) {
          if ((error as { name?: string } | null)?.name === 'AbortError' || sessionAbort.signal.aborted) {
            return;
          }
          message.error(t('common.operationFailed'));
        } finally {
          if (!sessionAbort.signal.aborted) {
            setLoading(false);
          }
        }
      }
    }));

    useEffect(() => {
      if (activeId != null) {
        const node = nodes.find((n) => n.id === activeId);
        if (node) loadNodeOptions(node, sessionAbortRef.current?.signal);
      }
    }, [activeId, nodes, loadNodeOptions]);

    const currentColumns = activeId != null ? columnsMap[activeId] || [] : [];
    const currentPlugins = activeId != null ? pluginsMap[activeId] || [] : [];

    const setCurrentColumns = (
      cols:
        | DisplayColumn[]
        | ((prev: DisplayColumn[]) => DisplayColumn[])
    ) => {
      const targetId = activeIdRef.current;
      if (targetId == null) return;
      dirtyRef.current.add(targetId);
      setColumnsMap((prev) => {
        const current = prev[targetId] || [];
        const nextCols = typeof cols === 'function' ? cols(current) : cols;
        const next = { ...prev, [targetId]: nextCols };
        columnsMapRef.current = next;
        return next;
      });
    };

    const addColumn = (type: DisplayColumn['type'] = 'metric') => {
      setCurrentColumns((cols) => [
        ...cols,
        {
          name:
            type === 'field'
              ? t('monitor.object.newFieldDisplayColumn')
              : t('monitor.object.newDisplayColumn'),
          ...(type === 'field' ? { type: 'field' } : {}),
          sort_order: cols.length,
          metrics: []
        }
      ]);
    };

    const removeColumn = (idx: number) => {
      setCurrentColumns((cols) =>
        cols.filter((_, i) => i !== idx).map((c, i) => ({ ...c, sort_order: i }))
      );
    };

    const updateColumnName = (idx: number, name: string) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) => (i === idx ? { ...c, name } : c))
      );
    };

    const updateColumnVariableId = (idx: number, variableId: string) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) => (i === idx ? { ...c, variable_id: variableId } : c))
      );
    };

    const addBinding = (colIdx: number) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) =>
          i === colIdx
            ? {
              ...c,
              metrics: [
                ...c.metrics,
                c.type === 'field'
                  ? { plugin: '', metric: '', field: '' }
                  : { plugin: '', metric: '' }
              ]
            }
            : c
        )
      );
    };

    const removeBinding = (colIdx: number, bindIdx: number) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) =>
          i === colIdx
            ? { ...c, metrics: c.metrics.filter((_, b) => b !== bindIdx) }
            : c
        )
      );
    };

    const metricsKey = (objId: number, plugin: string) => `${objId}|${plugin}`;

    const ensureMetrics = async (plugin: string, signal?: AbortSignal) => {
      if (activeId == null || !plugin) return [];
      const key = metricsKey(activeId, plugin);
      if (metricsMap[key]) return metricsMap[key];
      if (inflightMetricsRef.current.has(key)) return [];
      const pluginOpt = currentPlugins.find((p) => p.name === plugin);
      if (!pluginOpt) return [];
      const requestSignal = signal ?? sessionAbortRef.current?.signal;
      if (requestSignal?.aborted) return [];
      inflightMetricsRef.current.add(key);
      try {
        const boundMetricNames = currentColumns
          .flatMap((column) => column.metrics)
          .filter((binding) => binding.plugin === plugin && binding.metric)
          .map((binding) => binding.metric);
        const uniqueBoundMetricNames = [...new Set(boundMetricNames)];
        const boundMetricNameChunks = Array.from(
          { length: Math.ceil(uniqueBoundMetricNames.length / 100) },
          (_, index) => uniqueBoundMetricNames.slice(index * 100, (index + 1) * 100)
        );
        // 串行拉目录，避免交换机等对象一开弹窗对全部品牌并行打满连接。
        const firstPage = await getObjectMetrics(activeId, pluginOpt.id, {
          signal: requestSignal
        });
        if (requestSignal?.aborted) return [];
        const selectedPages = [];
        for (const names of boundMetricNameChunks) {
          if (requestSignal?.aborted) return [];
          selectedPages.push(
            await getObjectMetrics(activeId, pluginOpt.id, {
              name_in: names.join(','),
              signal: requestSignal
            })
          );
        }
        const metrics = [...firstPage.items];
        selectedPages.flatMap((page) => page.items).forEach((metric) => {
          if (!metrics.some((item) => item.id === metric.id)) {
            metrics.push(metric);
          }
        });
        setMetricsMap((prev) => ({ ...prev, [key]: metrics }));
        return metrics;
      } catch (error: unknown) {
        if ((error as { name?: string } | null)?.name === 'AbortError' || requestSignal?.aborted) {
          return [];
        }
        message.error(t('common.operationFailed'));
        return [];
      } finally {
        inflightMetricsRef.current.delete(key);
      }
    };

    // 预热已绑定指标：串行排队，点开下拉仍可懒加载。关弹窗 abort。
    useEffect(() => {
      if (activeId == null || currentPlugins.length === 0) return;
      const abort = new AbortController();
      const onSessionAbort = () => abort.abort();
      sessionAbortRef.current?.signal.addEventListener('abort', onSessionAbort);
      if (sessionAbortRef.current?.signal.aborted) {
        abort.abort();
      }
      const boundPlugins = [
        ...new Set(
          currentColumns
            .flatMap((c) => c.metrics)
            .map((m) => m.plugin)
            .filter(Boolean)
        )
      ];
      const warmup = async () => {
        for (const plugin of boundPlugins) {
          if (abort.signal.aborted) return;
          await ensureMetrics(plugin, abort.signal);
        }
      };
      void warmup();
      return () => {
        abort.abort();
        sessionAbortRef.current?.signal.removeEventListener('abort', onSessionAbort);
      };
      // ensureMetrics 依赖随渲染重建，且内部已用 metricsMap/inflight 双重去重，无需纳入依赖
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeId, currentPlugins, currentColumns]);

    const updateBindingPlugin = async (
      colIdx: number,
      bindIdx: number,
      plugin: string
    ) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) =>
          i === colIdx
            ? {
              ...c,
              metrics: c.metrics.map((b, j) =>
                j === bindIdx
                  ? c.type === 'field'
                    ? { plugin, metric: '', field: '' }
                    : { plugin, metric: '' }
                  : b
              )
            }
            : c
        )
      );
      await ensureMetrics(plugin);
    };

    const updateBindingMetric = (
      colIdx: number,
      bindIdx: number,
      metric: string
    ) => {
      const binding = currentColumns[colIdx]?.metrics[bindIdx];
      if (activeId != null && binding?.plugin) {
        const key = metricsKey(activeId, binding.plugin);
        const searchKey = `${key}|${colIdx}|${bindIdx}`;
        const selected = (metricSearchOptionsMap[searchKey] || []).find(
          (item) => item.name === metric
        );
        if (selected) {
          setSelectedMetricOptionsMap((prev) => ({
            ...prev,
            [searchKey]: selected
          }));
        }
      }
      setCurrentColumns((cols) =>
        cols.map((c, i) =>
          i === colIdx
            ? {
              ...c,
              metrics: c.metrics.map((b, j) =>
                j === bindIdx
                  ? { ...b, metric, ...(c.type === 'field' ? { field: '' } : {}) }
                  : b
              )
            }
            : c
        )
      );
    };

    const searchMetricOptions = (
      plugin: string,
      colIdx: number,
      bindIdx: number,
      keyword: string
    ) => {
      if (activeId == null || !plugin) return;
      const pluginOpt = currentPlugins.find((item) => item.name === plugin);
      if (!pluginOpt) return;
      const searchKey = `${metricsKey(activeId, plugin)}|${colIdx}|${bindIdx}`;
      const generation = (metricSearchGenerationRef.current[searchKey] || 0) + 1;
      metricSearchGenerationRef.current[searchKey] = generation;
      const previousTimer = metricSearchTimerRef.current[searchKey];
      if (previousTimer) clearTimeout(previousTimer);
      if (!keyword.trim()) {
        setMetricSearchOptionsMap((prev) => {
          const next = { ...prev };
          delete next[searchKey];
          return next;
        });
        return;
      }
      metricSearchTimerRef.current[searchKey] = setTimeout(async () => {
        try {
          const { items } = await getObjectMetrics(activeId, pluginOpt.id, {
            keyword: keyword.trim(),
            signal: sessionAbortRef.current?.signal
          });
          if (metricSearchGenerationRef.current[searchKey] !== generation) return;
          setMetricSearchOptionsMap((prev) => ({ ...prev, [searchKey]: items }));
        } catch (error: unknown) {
          if ((error as { name?: string } | null)?.name === 'AbortError') return;
          if (metricSearchGenerationRef.current[searchKey] !== generation) return;
          setMetricSearchOptionsMap((prev) => ({ ...prev, [searchKey]: [] }));
        }
      }, 300);
    };

    const updateBindingField = (
      colIdx: number,
      bindIdx: number,
      field: string
    ) => {
      setCurrentColumns((cols) =>
        cols.map((c, i) =>
          i === colIdx
            ? {
              ...c,
              metrics: c.metrics.map((b, j) =>
                j === bindIdx ? { ...b, field } : b
              )
            }
            : c
        )
      );
    };

    const findMetricOption = (
      plugin: string,
      metric: string,
      colIdx?: number,
      bindIdx?: number
    ) => metricsOptions(plugin, colIdx, bindIdx).find((m) => m.name === metric);

    const openFieldPicker = async (colIdx: number, bindIdx: number) => {
      const binding = currentColumns[colIdx]?.metrics[bindIdx];
      if (!binding?.plugin || !binding.metric) {
        message.warning(t('monitor.object.selectMetricFirst'));
        return;
      }
      const metrics = await ensureMetrics(binding.plugin);
      const metricOpt =
        metrics.find((m) => m.name === binding.metric) ||
        findMetricOption(binding.plugin, binding.metric, colIdx, bindIdx);
      if (!metricOpt) {
        message.warning(t('monitor.object.selectMetricFirst'));
        return;
      }
      setFieldPicker({
        visible: true,
        loading: true,
        fields: [],
        colIdx,
        bindIdx
      });
      try {
        const fields = await getMetricVmFields(
          metricOpt.id,
          sessionAbortRef.current?.signal
        );
        setFieldPicker((prev) => ({
          ...prev,
          loading: false,
          fields
        }));
      } catch {
        message.error(t('common.operationFailed'));
        setFieldPicker((prev) => ({ ...prev, loading: false }));
      }
    };

    const selectField = (field: string) => {
      updateBindingField(fieldPicker.colIdx, fieldPicker.bindIdx, field);
      setFieldPicker((prev) => ({ ...prev, visible: false }));
    };

    const renderFieldPicker = (selectedField?: string) => (
      <div className="w-[260px]">
        <Spin spinning={fieldPicker.loading}>
          {fieldPicker.fields.length ? (
            <div className="max-h-[240px] overflow-y-auto py-1">
              {fieldPicker.fields.map((field) => (
                <button
                  key={field}
                  type="button"
                  className={`block min-h-8 w-full rounded px-3 text-left text-sm leading-8 hover:bg-[var(--color-fill-1)] ${
                    selectedField === field
                      ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                      : 'text-[var(--color-text-1)]'
                  }`}
                  onClick={() => selectField(field)}
                >
                  {field}
                </button>
              ))}
            </div>
          ) : (
            <CompactEmptyState description={t('common.noData')} />
          )}
        </Spin>
      </div>
    );

    const onDragStart = (idx: number) => {
      dragIndexRef.current = idx;
    };

    const onDrop = (idx: number) => {
      const from = dragIndexRef.current;
      dragIndexRef.current = null;
      if (from == null || from === idx) return;
      setCurrentColumns((cols) => {
        const next = [...cols];
        const [moved] = next.splice(from, 1);
        next.splice(idx, 0, moved);
        return next.map((c, i) => ({ ...c, sort_order: i }));
      });
    };

    const handleCancel = () => {
      abortSession();
      setVisible(false);
      setNodes([]);
      columnsMapRef.current = {};
      activeIdRef.current = null;
      setColumnsMap({});
      setActiveId(null);
      dirtyRef.current = new Set();
    };

    const handleSubmit = async () => {
      setConfirmLoading(true);
      try {
        const currentId = activeIdRef.current;
        if (currentId != null) {
          dirtyRef.current.add(currentId);
        }
        const latest = columnsMapRef.current;
        for (const id of Array.from(dirtyRef.current)) {
          await saveDisplayFields(id, latest[id] || []);
        }
        invalidateMonitorObjectsCache();
        message.success(t('common.updateSuccess'));
        handleCancel();
        onSuccess?.();
      } catch {
        message.error(t('common.operationFailed'));
      } finally {
        setConfirmLoading(false);
      }
    };

    const showTree = nodes.length > 1;

    const metricsOptions = (plugin: string, colIdx?: number, bindIdx?: number) => {
      if (activeId == null) return [];
      const key = metricsKey(activeId, plugin);
      if (colIdx != null && bindIdx != null) {
        const bindingKey = `${key}|${colIdx}|${bindIdx}`;
        const options = metricSearchOptionsMap[bindingKey] || metricsMap[key] || [];
        const selected = selectedMetricOptionsMap[bindingKey];
        return selected && !options.some((item) => item.id === selected.id)
          ? [...options, selected]
          : options;
      }
      return metricsMap[key] || [];
    };

    return (
      <OperateModal
        width={900}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button className="mr-2" onClick={handleCancel}>
              {t('common.cancel')}
            </Button>
            <Button
              type="primary"
              loading={confirmLoading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
          </div>
        }
      >
        <Spin spinning={loading}>
          <div className="flex gap-4 min-h-[420px]">
            {showTree && (
              <div className="w-[220px] border-r border-[var(--color-border-2)] pr-3">
                <div className="text-xs text-[var(--color-text-3)] mb-2">
                  {t('monitor.object.configObject')}
                </div>
                {nodes.map((node) => {
                  const label = node.display_name || node.name;
                  const tip =
                    node.name && node.name !== label
                      ? `${label} (${node.name})`
                      : label;
                  return (
                    <div
                      key={node.id}
                      className={`flex items-center gap-1 px-2 py-1.5 rounded cursor-pointer mb-1 ${
                        activeId === node.id
                          ? 'bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
                          : 'hover:bg-[var(--color-fill-1)]'
                      }`}
                      onClick={() => setActiveId(node.id)}
                    >
                      <Tooltip title={tip}>
                        <span className="min-w-0 flex-1 truncate">{label}</span>
                      </Tooltip>
                      <Tag
                        className="shrink-0 m-0"
                        color={node.isBase ? 'blue' : 'default'}
                      >
                        {node.isBase
                          ? t('monitor.object.baseObject')
                          : t('monitor.object.childObject')}
                      </Tag>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="flex-1">
              <div className="flex justify-end gap-2 mb-3">
                <Button icon={<PlusOutlined />} onClick={() => addColumn('metric')}>
                  {t('monitor.object.addMetricColumn')}
                </Button>
                <Button icon={<PlusOutlined />} onClick={() => addColumn('field')}>
                  {t('monitor.object.addDisplayColumn')}
                </Button>
              </div>
              {currentColumns.map((col, colIdx) => (
                <div
                  key={colIdx}
                  className="border border-[var(--color-border-2)] rounded p-3 mb-3 bg-[var(--color-fill-1)]"
                  draggable
                  onDragStart={() => onDragStart(colIdx)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => onDrop(colIdx)}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <HolderOutlined className="cursor-move text-[var(--color-text-3)]" />
                    <Input
                      className="flex-1"
                      value={col.name}
                      placeholder={t(
                        'monitor.object.displayColumnNamePlaceholder'
                      )}
                      onChange={(e) => updateColumnName(colIdx, e.target.value)}
                    />
                    <Input
                      className="w-[160px]"
                      value={col.variable_id || ''}
                      placeholder={t('monitor.object.variableIdPlaceholder')}
                      onChange={(e) =>
                        updateColumnVariableId(colIdx, e.target.value)
                      }
                    />
                    {col.variable_id ? (
                      <span className="font-mono text-xs text-[var(--color-text-3)]">
                        {`\${${col.variable_id}}`}
                      </span>
                    ) : null}
                    <Button
                      type="text"
                      danger
                      icon={<CloseOutlined />}
                      onClick={() => removeColumn(colIdx)}
                    />
                  </div>
                  {col.metrics.map((binding, bindIdx) => (
                    <div
                      key={bindIdx}
                      className="flex items-center gap-2 mb-2 pl-6"
                    >
                      <Select
                        className="flex-1"
                        showSearch
                        optionFilterProp="label"
                        value={binding.plugin || undefined}
                        placeholder={t('monitor.object.selectTemplate')}
                        options={currentPlugins.map((p) => ({
                          label: p.display_name || p.name,
                          value: p.name
                        }))}
                        onChange={(v) =>
                          updateBindingPlugin(colIdx, bindIdx, v)
                        }
                      />
                      <Select
                        className="flex-1"
                        showSearch
                        filterOption={false}
                        value={binding.metric || undefined}
                        placeholder={t('monitor.object.selectMetric')}
                        disabled={!binding.plugin}
                        options={metricsOptions(binding.plugin, colIdx, bindIdx).map((m) => ({
                          label: m.display_name || m.name,
                          value: m.name
                        }))}
                        onSearch={(value) =>
                          searchMetricOptions(binding.plugin, colIdx, bindIdx, value)
                        }
                        onDropdownVisibleChange={(open) => {
                          if (open) {
                            ensureMetrics(binding.plugin);
                          } else {
                            searchMetricOptions(binding.plugin, colIdx, bindIdx, '');
                          }
                        }}
                        onChange={(v) =>
                          updateBindingMetric(colIdx, bindIdx, v)
                        }
                      />
                      {col.type === 'field' && (
                        <Input
                          className="flex-1"
                          value={binding.field}
                          placeholder={t('monitor.object.fieldKeyPlaceholder')}
                          onChange={(e) =>
                            updateBindingField(colIdx, bindIdx, e.target.value)
                          }
                          addonAfter={
                            <Popover
                              trigger="click"
                              placement="bottomRight"
                              content={renderFieldPicker(binding.field)}
                              open={
                                fieldPicker.visible &&
                                fieldPicker.colIdx === colIdx &&
                                fieldPicker.bindIdx === bindIdx
                              }
                              onOpenChange={(open) => {
                                if (open) {
                                  openFieldPicker(colIdx, bindIdx);
                                  return;
                                }
                                setFieldPicker((prev) => ({ ...prev, visible: false }));
                              }}
                            >
                              <Button type="link" size="small" className="px-0">
                                {t('monitor.object.selectField')}
                              </Button>
                            </Popover>
                          }
                        />
                      )}
                      <Button
                        type="text"
                        danger
                        icon={<CloseOutlined />}
                        onClick={() => removeBinding(colIdx, bindIdx)}
                      />
                    </div>
                  ))}
                  <Button
                    type="dashed"
                    size="small"
                    icon={<PlusOutlined />}
                    className="ml-6"
                    onClick={() => addBinding(colIdx)}
                  >
                    {t('monitor.object.addMetric')}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </Spin>
      </OperateModal>
    );
  }
);

DisplayFieldsModal.displayName = 'DisplayFieldsModal';
export default DisplayFieldsModal;
