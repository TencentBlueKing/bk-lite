'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useCallback
} from 'react';
import { Input, Button, Select, message, Spin, Tag, Radio, Empty } from 'antd';
import { PlusOutlined, CloseOutlined, HolderOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import { ModalRef, ModalConfig } from '@/app/monitor/types';
import {
  MonitorObjectItem,
  DisplayColumn,
  PluginOption,
  MetricOption
} from './types';
import { useTranslation } from '@/utils/i18n';
import useObjectApi from './api';

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
    const [fieldPicker, setFieldPicker] = useState<{
      visible: boolean;
      loading: boolean;
      fields: string[];
      value: string;
      colIdx: number;
      bindIdx: number;
    }>({
      visible: false,
      loading: false,
      fields: [],
      value: '',
      colIdx: -1,
      bindIdx: -1
    });
    const dragIndexRef = useRef<number | null>(null);
    // 镜像 pluginsMap，供 loadNodeOptions 同步读取已加载状态（避免在 setState updater 内做副作用）
    const pluginsMapRef = useRef<Record<number, PluginOption[]>>({});
    // 正在请求中的指标 key，避免预热与下拉懒加载并发重复请求同一插件
    const inflightMetricsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
      pluginsMapRef.current = pluginsMap;
    }, [pluginsMap]);

    const loadNodeOptions = useCallback(
      async (node: ConfigObjectNode) => {
        if (pluginsMapRef.current[node.id]) return;
        try {
          const plugins = await getObjectPlugins(node.id);
          setPluginsMap((p) => ({ ...p, [node.id]: plugins || [] }));
        } catch {
          message.error(t('common.operationFailed'));
        }
      },
      [getObjectPlugins, t]
    );

    useImperativeHandle(ref, () => ({
      showModal: async ({ form }: ModalConfig) => {
        const obj = form as MonitorObjectItem;
        setVisible(true);
        setLoading(true);
        dirtyRef.current = new Set();
        pluginsMapRef.current = {};
        inflightMetricsRef.current = new Set();
        setColumnsMap({});
        setPluginsMap({});
        setMetricsMap({});
        setFieldPicker({
          visible: false,
          loading: false,
          fields: [],
          value: '',
          colIdx: -1,
          bindIdx: -1
        });
        setTitle(
          `${t('monitor.object.displayFieldsConfig')} - ${obj.display_name || obj.name}`
        );
        try {
          const baseDetail = await getObjectDetail(obj.id);
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
            const children = await getObjectChildrenRaw(obj.id);
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
          setColumnsMap(initColumns);
          setActiveId(obj.id);
          await loadNodeOptions(baseNode);
        } catch {
          message.error(t('common.operationFailed'));
        } finally {
          setLoading(false);
        }
      }
    }));

    useEffect(() => {
      if (activeId != null) {
        const node = nodes.find((n) => n.id === activeId);
        if (node) loadNodeOptions(node);
      }
    }, [activeId, nodes, loadNodeOptions]);

    const currentColumns = activeId != null ? columnsMap[activeId] || [] : [];
    const currentPlugins = activeId != null ? pluginsMap[activeId] || [] : [];

    const setCurrentColumns = (cols: DisplayColumn[]) => {
      if (activeId == null) return;
      dirtyRef.current.add(activeId);
      setColumnsMap((prev) => ({ ...prev, [activeId]: cols }));
    };

    const addColumn = (type: DisplayColumn['type'] = 'metric') => {
      setCurrentColumns([
        ...currentColumns,
        {
          name:
            type === 'field'
              ? t('monitor.object.newFieldDisplayColumn')
              : t('monitor.object.newDisplayColumn'),
          ...(type === 'field' ? { type: 'field' } : {}),
          sort_order: currentColumns.length,
          metrics: []
        }
      ]);
    };

    const removeColumn = (idx: number) => {
      setCurrentColumns(
        currentColumns
          .filter((_, i) => i !== idx)
          .map((c, i) => ({ ...c, sort_order: i }))
      );
    };

    const updateColumnName = (idx: number, name: string) => {
      setCurrentColumns(
        currentColumns.map((c, i) => (i === idx ? { ...c, name } : c))
      );
    };

    const addBinding = (colIdx: number) => {
      setCurrentColumns(
        currentColumns.map((c, i) =>
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
      setCurrentColumns(
        currentColumns.map((c, i) =>
          i === colIdx
            ? { ...c, metrics: c.metrics.filter((_, b) => b !== bindIdx) }
            : c
        )
      );
    };

    const metricsKey = (objId: number, plugin: string) => `${objId}|${plugin}`;

    const ensureMetrics = async (plugin: string) => {
      if (activeId == null || !plugin) return [];
      const key = metricsKey(activeId, plugin);
      if (metricsMap[key]) return metricsMap[key];
      if (inflightMetricsRef.current.has(key)) return [];
      const pluginOpt = currentPlugins.find((p) => p.name === plugin);
      if (!pluginOpt) return [];
      inflightMetricsRef.current.add(key);
      try {
        const metrics = await getObjectMetrics(activeId, pluginOpt.id);
        setMetricsMap((prev) => ({ ...prev, [key]: metrics || [] }));
        return metrics || [];
      } catch {
        message.error(t('common.operationFailed'));
        return [];
      } finally {
        inflightMetricsRef.current.delete(key);
      }
    };

    // 预热已绑定指标的插件选项：否则初次渲染时 Select 的 value（指标原始名）在空 options
    // 里匹配不到对应项，antd 会回退显示原始名（英文），点开下拉懒加载后才变成中文展示名。
    useEffect(() => {
      if (activeId == null || currentPlugins.length === 0) return;
      const boundPlugins = new Set(
        currentColumns
          .flatMap((c) => c.metrics)
          .map((m) => m.plugin)
          .filter(Boolean)
      );
      boundPlugins.forEach((plugin) => ensureMetrics(plugin));
      // ensureMetrics 依赖随渲染重建，且内部已用 metricsMap/inflight 双重去重，无需纳入依赖
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeId, currentPlugins, currentColumns]);

    const updateBindingPlugin = async (
      colIdx: number,
      bindIdx: number,
      plugin: string
    ) => {
      setCurrentColumns(
        currentColumns.map((c, i) =>
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
      setCurrentColumns(
        currentColumns.map((c, i) =>
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

    const updateBindingField = (
      colIdx: number,
      bindIdx: number,
      field: string
    ) => {
      setCurrentColumns(
        currentColumns.map((c, i) =>
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

    const findMetricOption = (plugin: string, metric: string) =>
      metricsOptions(plugin).find((m) => m.name === metric);

    const openFieldPicker = async (colIdx: number, bindIdx: number) => {
      const binding = currentColumns[colIdx]?.metrics[bindIdx];
      if (!binding?.plugin || !binding.metric) {
        message.warning(t('monitor.object.selectMetricFirst'));
        return;
      }
      const metrics = await ensureMetrics(binding.plugin);
      const metricOpt =
        metrics.find((m) => m.name === binding.metric) ||
        findMetricOption(binding.plugin, binding.metric);
      if (!metricOpt) {
        message.warning(t('monitor.object.selectMetricFirst'));
        return;
      }
      setFieldPicker({
        visible: true,
        loading: true,
        fields: [],
        value: binding.field || '',
        colIdx,
        bindIdx
      });
      try {
        const fields = await getMetricVmFields(metricOpt.id);
        setFieldPicker((prev) => ({
          ...prev,
          loading: false,
          fields,
          value: prev.value || fields[0] || ''
        }));
      } catch {
        message.error(t('common.operationFailed'));
        setFieldPicker((prev) => ({ ...prev, loading: false }));
      }
    };

    const confirmFieldPicker = () => {
      if (fieldPicker.colIdx >= 0 && fieldPicker.bindIdx >= 0) {
        updateBindingField(
          fieldPicker.colIdx,
          fieldPicker.bindIdx,
          fieldPicker.value
        );
      }
      setFieldPicker((prev) => ({ ...prev, visible: false }));
    };

    const onDragStart = (idx: number) => {
      dragIndexRef.current = idx;
    };

    const onDrop = (idx: number) => {
      const from = dragIndexRef.current;
      dragIndexRef.current = null;
      if (from == null || from === idx) return;
      const next = [...currentColumns];
      const [moved] = next.splice(from, 1);
      next.splice(idx, 0, moved);
      setCurrentColumns(next.map((c, i) => ({ ...c, sort_order: i })));
    };

    const handleCancel = () => {
      setVisible(false);
      setNodes([]);
      setColumnsMap({});
      setActiveId(null);
      dirtyRef.current = new Set();
    };

    const handleSubmit = async () => {
      setConfirmLoading(true);
      try {
        for (const id of Array.from(dirtyRef.current)) {
          await saveDisplayFields(id, columnsMap[id] || []);
        }
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

    const metricsOptions = (plugin: string) =>
      activeId != null ? metricsMap[metricsKey(activeId, plugin)] || [] : [];

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
              <div className="w-[180px] border-r border-[var(--color-border-2)] pr-3">
                <div className="text-xs text-[var(--color-text-3)] mb-2">
                  {t('monitor.object.configObject')}
                </div>
                {nodes.map((node) => (
                  <div
                    key={node.id}
                    className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer mb-1 ${
                      activeId === node.id
                        ? 'bg-[#e6f4ff] text-[#1890ff]'
                        : 'hover:bg-[var(--color-fill-1)]'
                    }`}
                    onClick={() => setActiveId(node.id)}
                  >
                    <span className="truncate">{node.display_name}</span>
                    <Tag color={node.isBase ? 'blue' : 'default'}>
                      {node.isBase
                        ? t('monitor.object.baseObject')
                        : t('monitor.object.childObject')}
                    </Tag>
                  </div>
                ))}
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
                        optionFilterProp="label"
                        value={binding.metric || undefined}
                        placeholder={t('monitor.object.selectMetric')}
                        disabled={!binding.plugin}
                        onDropdownVisibleChange={(open) =>
                          open && ensureMetrics(binding.plugin)
                        }
                        options={metricsOptions(binding.plugin).map((m) => ({
                          label: m.display_name || m.name,
                          value: m.name
                        }))}
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
                            <Button
                              type="link"
                              size="small"
                              className="px-0"
                              onClick={() => openFieldPicker(colIdx, bindIdx)}
                            >
                              {t('monitor.object.selectField')}
                            </Button>
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
        <OperateModal
          width={520}
          title={t('monitor.object.selectField')}
          visible={fieldPicker.visible}
          onCancel={() => setFieldPicker((prev) => ({ ...prev, visible: false }))}
          footer={
            <div>
              <Button
                className="mr-2"
                onClick={() => setFieldPicker((prev) => ({ ...prev, visible: false }))}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="primary"
                loading={fieldPicker.loading}
                disabled={!fieldPicker.value}
                onClick={confirmFieldPicker}
              >
                {t('common.confirm')}
              </Button>
            </div>
          }
        >
          <Spin spinning={fieldPicker.loading}>
            {fieldPicker.fields.length ? (
              <Radio.Group
                className="flex max-h-[320px] flex-col overflow-y-auto"
                value={fieldPicker.value}
                onChange={(e) =>
                  setFieldPicker((prev) => ({ ...prev, value: e.target.value }))
                }
              >
                {fieldPicker.fields.map((field) => (
                  <Radio
                    key={field}
                    value={field}
                    className="mx-0 flex min-h-9 items-center rounded px-2 hover:bg-[var(--color-fill-1)]"
                  >
                    {field}
                  </Radio>
                ))}
              </Radio.Group>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Spin>
        </OperateModal>
      </OperateModal>
    );
  }
);

DisplayFieldsModal.displayName = 'DisplayFieldsModal';
export default DisplayFieldsModal;
