'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useCallback
} from 'react';
import { Input, Button, Select, message, Spin, Tag } from 'antd';
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
    const dragIndexRef = useRef<number | null>(null);
    // 镜像 pluginsMap，供 loadNodeOptions 同步读取已加载状态（避免在 setState updater 内做副作用）
    const pluginsMapRef = useRef<Record<number, PluginOption[]>>({});

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
        setColumnsMap({});
        setPluginsMap({});
        setMetricsMap({});
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

    const addColumn = () => {
      setCurrentColumns([
        ...currentColumns,
        {
          name: t('monitor.object.newDisplayColumn'),
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
            ? { ...c, metrics: [...c.metrics, { plugin: '', metric: '' }] }
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
      if (activeId == null || !plugin) return;
      const key = metricsKey(activeId, plugin);
      if (metricsMap[key]) return;
      const pluginOpt = currentPlugins.find((p) => p.name === plugin);
      if (!pluginOpt) return;
      try {
        const metrics = await getObjectMetrics(activeId, pluginOpt.id);
        setMetricsMap((prev) => ({ ...prev, [key]: metrics || [] }));
      } catch {
        message.error(t('common.operationFailed'));
      }
    };

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
                j === bindIdx ? { plugin, metric: '' } : b
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
                j === bindIdx ? { ...b, metric } : b
              )
            }
            : c
        )
      );
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
              <div className="flex justify-end mb-3">
                <Button icon={<PlusOutlined />} onClick={addColumn}>
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
