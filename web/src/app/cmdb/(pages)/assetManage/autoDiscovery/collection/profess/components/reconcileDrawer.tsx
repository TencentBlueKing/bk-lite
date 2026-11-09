'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Drawer, Input, Modal, Select, Table, Tag, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCollectApi } from '@/app/cmdb/api';

interface Member {
  id: number;
  name: string;
  collected_fields: string[];
  position: number;
  plugin_key?: string;
  plugin_name?: string;
  model_id?: string;
  task_type?: string;
  driver_type?: string;
  custom_plugin_pk?: number | null;
};
interface PluginOption {
  id: string;
  name: string;
  model_id?: string;
  target_model_id?: string;
  type?: string;
  task_type?: string;
  custom_plugin_pk?: number;
};
interface PluginGroup {
  id: string;
  name: string;
  plugins: PluginOption[];
};
interface FieldOrder { field: string; tasks: { id: number; name: string }[] }
interface Reconcile {
  id: number;
  name: string;
  model_id: string;
  version: number;
  effective: boolean;
  members: Member[];
  field_orders?: FieldOrder[];
  can_edit_all_members: boolean;
};
interface Candidate {
  id: number;
  name: string;
  ip_range?: string;
  collected_fields?: string[];
  in_reconcile: boolean;
  plugin_key: string;
  plugin_name?: string;
  task_type?: string;
  driver_type?: string;
  model_id?: string;
  custom_plugin_pk?: number | null;
};
type Mode = 'list' | 'form' | 'detail';

const move = <T,>(items: T[], index: number, direction: -1 | 1) => {
  const next = index + direction;
  if (next < 0 || next >= items.length) {
    return items;
  }
  const copy = [...items];
  const [item] = copy.splice(index, 1);
  copy.splice(next, 0, item);
  return copy;
};

const errorText = (error: unknown) => (error instanceof Error ? error.message : '');

const pluginLabel = (item: Candidate | Member, plugins: PluginOption[]) => {
  const customPk = item.custom_plugin_pk;
  if (customPk) {
    const custom = plugins.find((plugin) => plugin.custom_plugin_pk === customPk);
    if (custom?.name) return custom.name;
  }
  const byId = 'plugin_key' in item ? plugins.find((plugin) => plugin.id === item.plugin_key) : undefined;
  if (byId?.name) return byId.name;
  const typed = plugins.find((plugin) => (
    plugin.task_type === item.task_type
    && (plugin.model_id === ('model_id' in item ? item.model_id : undefined) || plugin.id === ('model_id' in item ? item.model_id : undefined))
    && (!plugin.type || !item.driver_type || plugin.type === item.driver_type)
  ));
  if (typed?.name) return typed.name;
  return item.plugin_name || ('plugin_key' in item ? item.plugin_key : '') || '';
};

const pluginModelId = (plugin: PluginOption) => plugin.model_id || plugin.target_model_id || plugin.id;

const taskOfPlugin = (task: Candidate, plugin: PluginOption) => {
  if (plugin.custom_plugin_pk && task.custom_plugin_pk === plugin.custom_plugin_pk) return true;
  if (plugin.id && plugin.id === task.plugin_key) return true;
  return plugin.task_type === task.task_type
    && (plugin.model_id === task.model_id || plugin.id === task.model_id)
    && (!plugin.type || !task.driver_type || plugin.type === task.driver_type);
};

const ReconcileDrawer: React.FC<{
  open: boolean;
  modelId: string;
  modelName: string;
  groups?: PluginGroup[];
  onClose: () => void;
}> = ({ open, modelId, modelName, groups = [], onClose }) => {
  const { t } = useTranslation();
  const api = useCollectApi();
  const [mode, setMode] = useState<Mode>('list');
  const [items, setItems] = useState<Reconcile[]>([]);
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [pluginIds, setPluginIds] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [current, setCurrent] = useState<Reconcile | null>(null);
  const [draft, setDraft] = useState(false);
  const [editingField, setEditingField] = useState<string | null>(null);

  const loadList = async () => {
    if (!modelId) {
      setItems([]);
      return;
    }
    setLoading(true);
    try {
      const data = await api.listCollectReconcile(modelId);
      setItems(data?.items || []);
    } catch (error) {
      message.error(errorText(error) || t('Collection.reconcileEmpty'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    setMode('list');
    setCurrent(null);
    setEditingField(null);
    setName('');
    setSelected([]);
    setGroupIds([]);
    setPluginIds([]);
    setDraft(false);
    loadList();
  }, [open, modelId]);

  const openForm = () => {
    setName('');
    setSelected([]);
    setGroupIds([]);
    setPluginIds([]);
    setCandidates([]);
    setDraft(false);
    setMode('form');
  };

  const catalogPlugins = useMemo(() => groups.flatMap((group) => group.plugins), [groups]);
  const selectedPlugins = catalogPlugins.filter((plugin) => pluginIds.includes(plugin.id));
  const selectedModels = [...new Set(selectedPlugins.map(pluginModelId))];

  useEffect(() => {
    if (mode !== 'form' || selectedModels.length === 0) {
      return;
    }
    let cancelled = false;
    Promise.all(selectedModels.map((id) => api.getReconcileCandidates(id)))
      .then((batches) => {
        if (!cancelled) setCandidates(batches.flat());
      })
      .catch((error) => {
        if (!cancelled) {
          setCandidates([]);
          message.error(errorText(error) || t('Collection.reconcileEmpty'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, selectedModels.join('|')]);

  const chosenTasks = candidates.filter((task) => (
    selected.includes(task.id)
    && !task.in_reconcile
    && selectedPlugins.some((plugin) => taskOfPlugin(task, plugin))
  ));
  const chosenModels = [...new Set(chosenTasks.map((task) => task.model_id).filter(Boolean))];
  const readyToConfigure = Boolean(name.trim())
    && groupIds.length >= 1
    && selectedPlugins.length >= 1
    && chosenTasks.length >= 1;

  const goConfigure = () => {
    if (!readyToConfigure) {
      message.warning(t('Collection.reconcileNeedTwo'));
      return;
    }
    const chosen = chosenTasks;
    const members: Member[] = chosen.map((item, index) => ({
      id: item.id,
      name: item.name,
      collected_fields: item.collected_fields || [],
      position: index,
      plugin_key: item.plugin_key,
      plugin_name: pluginLabel(item, catalogPlugins),
      model_id: item.model_id,
      task_type: item.task_type,
      driver_type: item.driver_type,
      custom_plugin_pk: item.custom_plugin_pk,
    }));
    const fieldOrders: FieldOrder[] = [];
    members.forEach((member) => {
      member.collected_fields.forEach((field) => {
        const existing = fieldOrders.find((item) => item.field === field);
        const task = { id: member.id, name: member.name };
        if (existing) {
          existing.tasks.push(task);
          return;
        }
        fieldOrders.push({ field, tasks: [task] });
      });
    });
    setCurrent({
      id: 0,
      name: name.trim(),
      model_id: chosenModels[0] || modelId,
      version: 0,
      effective: members.length >= 2,
      members,
      field_orders: fieldOrders,
      can_edit_all_members: true,
    });
    setEditingField(null);
    setDraft(true);
    setMode('detail');
  };

  const createDraft = async () => {
    if (!current) {
      return;
    }
    const models = [...new Set(current.members.map((member) => member.model_id).filter(Boolean))];
    if (models.length > 1) {
      message.error(t('Collection.reconcileMixedModel'));
      return;
    }
    const fieldOrders: Record<string, number[]> = {};
    (current.field_orders || []).forEach((item) => {
      fieldOrders[item.field] = item.tasks.map((task) => task.id);
    });
    setSaving(true);
    try {
      await api.createCollectReconcile({
        name: current.name,
        model_id: current.model_id || modelId,
        task_ids: current.members.map((member) => member.id),
        ...(Object.keys(fieldOrders).length ? { field_orders: fieldOrders } : {}),
      });
      setDraft(false);
      setCurrent(null);
      setEditingField(null);
      setMode('list');
      await loadList();
      message.success(t('Collection.reconcileFinish'));
    } catch (error) {
      message.error(errorText(error) || t('Collection.reconcileNeedTwo'));
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (id: number) => {
    try {
      setDraft(false);
      setCurrent(await api.getCollectReconcile(id));
      setEditingField(null);
      setMode('detail');
    } catch (error) {
      message.error(errorText(error) || t('Collection.reconcileEmpty'));
    }
  };

  const saveDetail = async () => {
    if (!current) {
      return;
    }
    const fieldOrders: Record<string, number[]> = {};
    (current.field_orders || []).forEach((item) => {
      if (item.tasks.length > 1) {
        fieldOrders[item.field] = item.tasks.map((task) => task.id);
      }
    });
    setSaving(true);
    try {
      const saved = await api.updateCollectReconcile(current.id, {
        version: current.version,
        task_ids: current.members.map((member) => member.id),
        field_orders: current.can_edit_all_members ? fieldOrders : undefined,
      });
      setCurrent(saved);
      await loadList();
      message.success(t('Collection.reconcileSave'));
    } catch (error) {
      message.error(errorText(error) || t('Collection.reconcileEmpty'));
    } finally {
      setSaving(false);
    }
  };

  const removeReconcile = (id: number) => {
    Modal.confirm({
      title: t('Collection.reconcileDeleteConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        await api.deleteCollectReconcile(id);
        message.success(t('successfullyDeleted'));
        await loadList();
      },
    });
  };

  const goBack = () => {
    setEditingField(null);
    if (mode === 'detail' && draft) {
      setMode('form');
      return;
    }
    setDraft(false);
    setMode('list');
  };

  const screenTitle = mode === 'form'
    ? t('Collection.reconcileCreate')
    : mode === 'detail' && current
      ? current.name
      : t('Collection.reconcileTitle');
  const modelLabel = modelName || modelId;
  const labelPlugin = (item: Candidate | Member) => pluginLabel({ ...item, model_id: item.model_id || modelId, plugin_key: item.plugin_key || '' }, catalogPlugins);
  const memberText = (member: Member) => {
    const plugin = labelPlugin(member);
    return plugin ? `${plugin}：${member.name}` : member.name;
  };

  return (
    <Drawer title={t('Collection.reconcileTitle')} open={open} onClose={onClose} width={840}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="m-0 text-base font-medium">{screenTitle}</h2>
        {mode === 'list' ? (
          <Button type="primary" onClick={openForm}>{t('Collection.reconcileCreate')}</Button>
        ) : (
          <Button onClick={goBack}>
            {mode === 'detail' && draft ? t('Collection.reconcilePrev') : t('Collection.reconcileBack')}
          </Button>
        )}
      </div>

      {mode === 'list' ? (
        <>
          <p className="mb-3 text-[13px] text-[var(--color-text-2)]">{t('Collection.reconcileListHint')}</p>
          <table className="w-full border-collapse border border-[var(--color-border-1)] text-sm">
            <thead>
              <tr className="text-left text-[var(--color-text-2)]">
                <th className="border-b border-[var(--color-border-1)] px-3 py-2.5 font-medium">{t('Collection.reconcileName')}</th>
                <th className="border-b border-[var(--color-border-1)] px-3 py-2.5 font-medium">{t('Collection.reconcileModel')}</th>
                <th className="border-b border-[var(--color-border-1)] px-3 py-2.5 font-medium">{t('Collection.reconcileMemberColumn')}</th>
                <th className="border-b border-[var(--color-border-1)] px-3 py-2.5 font-medium">{t('Collection.reconcileStatus')}</th>
                <th className="border-b border-[var(--color-border-1)] px-3 py-2.5 font-medium" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td className="px-3 py-2.5" colSpan={5}>{t('Collection.reconcileEmpty')}</td></tr>
              ) : null}
              {!loading && items.length === 0 ? (
                <tr><td className="px-3 py-2.5" colSpan={5}>{t('Collection.reconcileEmpty')}</td></tr>
              ) : null}
              {!loading && items.map((item) => (
                <tr key={item.id}>
                  <td className="border-b border-[var(--color-border-1)] px-3 py-2.5">{item.name}</td>
                  <td className="border-b border-[var(--color-border-1)] px-3 py-2.5">{modelLabel}</td>
                  <td className="border-b border-[var(--color-border-1)] px-3 py-2.5">{item.members.map(memberText).join('、') || '--'}</td>
                  <td className="border-b border-[var(--color-border-1)] px-3 py-2.5">
                    {item.effective
                      ? <Tag color="success">{t('Collection.reconcileStatusOn')}</Tag>
                      : <Tag>{t('Collection.reconcileStatusOff')}</Tag>}
                  </td>
                  <td className="border-b border-[var(--color-border-1)] px-3 py-2.5">
                    <Button onClick={() => openDetail(item.id)}>{t('Collection.reconcileConfigure')}</Button>
                    <Button danger className="ml-2" onClick={() => removeReconcile(item.id)}>{t('Collection.reconcileDelete')}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {mode === 'form' ? (
        <div className="rounded-lg border border-[var(--color-border-1)] p-4">
          <label className="mb-3 block">
            <span className="mb-1 block">{t('Collection.reconcileName')}</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <p className="mb-3 text-[13px] text-[var(--color-text-2)]">{t('Collection.reconcilePickHint')}</p>
          <label className="mb-3 block">
            <span className="mb-1 block">{t('Collection.reconcileGroups')}</span>
            <Select
              className="w-full"
              mode="multiple"
              allowClear
              value={groupIds}
              placeholder={t('Collection.reconcileGroups')}
              options={groups.map((group) => ({ value: group.id, label: group.name }))}
              onChange={(ids: string[]) => {
                setGroupIds(ids);
                const allowedPlugins = groups.filter((group) => ids.includes(group.id)).flatMap((group) => group.plugins);
                const allowed = new Set(allowedPlugins.map((plugin) => plugin.id));
                setPluginIds((currentIds) => currentIds.filter((id) => allowed.has(id)));
                setSelected((currentIds) => currentIds.filter((id) => {
                  const task = candidates.find((item) => item.id === id);
                  return Boolean(task && allowedPlugins.some((plugin) => taskOfPlugin(task, plugin)));
                }));
              }}
            />
          </label>
          <label className="mb-3 block">
            <span className="mb-1 block">{t('Collection.reconcilePlugins')}</span>
            <Select
              className="w-full"
              mode="multiple"
              allowClear
              disabled={groupIds.length < 1}
              value={pluginIds}
              placeholder={t('Collection.reconcilePlugins')}
              options={groups.filter((group) => groupIds.includes(group.id)).flatMap((group) => group.plugins.map((plugin) => ({ value: plugin.id, label: plugin.name })))}
              onChange={(ids: string[]) => {
                setPluginIds(ids);
                const kept = catalogPlugins.filter((plugin) => ids.includes(plugin.id));
                setSelected((currentIds) => currentIds.filter((id) => {
                  const task = candidates.find((item) => item.id === id);
                  return Boolean(task && kept.some((plugin) => taskOfPlugin(task, plugin)));
                }));
              }}
            />
          </label>
          <Table
            className="mb-3"
            rowKey="id"
            pagination={false}
            dataSource={candidates.filter((task) => selectedPlugins.some((plugin) => taskOfPlugin(task, plugin)))}
            locale={{ emptyText: t('Collection.reconcileEmpty') }}
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys.map(Number)),
              getCheckboxProps: (record: Candidate) => ({ disabled: record.in_reconcile }),
            }}
            columns={[
              {
                title: t('Collection.reconcilePlugins'),
                dataIndex: 'plugin_key',
                render: (_value: string, record: Candidate) => pluginLabel(record, catalogPlugins),
              },
              { title: t('Collection.reconcileName'), dataIndex: 'name' },
              { title: t('Collection.reconcileRange'), dataIndex: 'ip_range', render: (value: string) => value || '--' },
              {
                title: t('Collection.reconcileStatus'),
                dataIndex: 'in_reconcile',
                render: (taken: boolean) => (taken ? t('Collection.reconcileTaskTaken') : '--'),
              },
            ]}
          />
          <Button type="primary" disabled={!readyToConfigure} onClick={goConfigure}>
            {t('Collection.reconcileNext')}
          </Button>
        </div>
      ) : null}

      {mode === 'detail' && current ? (
        <div className="flex flex-col gap-4">
          {draft && new Set(current.members.map((member) => member.model_id).filter(Boolean)).size > 1 ? (
            <Alert type="warning" showIcon message={t('Collection.reconcileMixedModel')} />
          ) : null}
          {!current.effective ? <Alert type="warning" showIcon message={t('Collection.reconcileStopped')} /> : null}
          <div className="flex flex-col gap-4">
            <section className="rounded-lg border border-[var(--color-border-1)] p-4">
              <div className="font-medium">{t('Collection.reconcileMembers')}</div>
              <p className="mb-3 text-[13px] text-[var(--color-text-2)]">{t('Collection.reconcileMemberHint')}</p>
              {current.members.map((member, index) => (
                <div key={member.id} className="mb-2 flex items-center justify-between gap-2 rounded border border-[var(--color-border-1)] px-3 py-2">
                  <span>{index + 1}. {memberText(member)}</span>
                  <span className="flex gap-1">
                    <Button size="small" onClick={() => setCurrent({ ...current, members: move(current.members, index, -1) })}>{t('Collection.reconcileMoveUp')}</Button>
                    <Button size="small" onClick={() => setCurrent({ ...current, members: move(current.members, index, 1) })}>{t('Collection.reconcileMoveDown')}</Button>
                  </span>
                </div>
              ))}
            </section>
            <section className="rounded-lg border border-[var(--color-border-1)] p-4">
              <div className="font-medium">{t('Collection.reconcileFields')}</div>
              <p className="mb-3 text-[13px] text-[var(--color-text-2)]">{t('Collection.reconcileFieldHint')}</p>
              <Table
                rowKey="field"
                pagination={false}
                dataSource={current.field_orders || []}
                columns={[
                  { title: t('Collection.reconcileFieldColumn'), dataIndex: 'field' },
                  {
                    title: t('Collection.reconcileFieldOrder'),
                    dataIndex: 'tasks',
                    render: (tasks: { id: number; name: string }[]) => tasks.map((task) => {
                      const member = current.members.find((item) => item.id === task.id);
                      return member ? memberText(member) : task.name;
                    }).join(' > ') || '--',
                  },
                  {
                    title: '',
                    key: 'adjust',
                    render: (_, field: FieldOrder) => (
                      <Button
                        size="small"
                        disabled={field.tasks.length < 2 || (!draft && (!current.can_edit_all_members || !current.effective))}
                        onClick={() => setEditingField(field.field)}
                      >
                        {field.tasks.length > 1 ? t('Collection.reconcileAdjustField') : t('Collection.reconcileOnlyOne')}
                      </Button>
                    ),
                  },
                ]}
              />
              {editingField ? (
                <div className="mt-4">
                  <div className="mb-2 font-medium">{editingField}</div>
                  {(current.field_orders || []).find((item) => item.field === editingField)?.tasks.map((task, index, tasks) => (
                    <div key={task.id} className="mb-2 flex items-center justify-between gap-2 rounded border border-[var(--color-border-1)] px-3 py-2">
                      <span>{index + 1}. {(() => {
                        const member = current.members.find((item) => item.id === task.id);
                        return member ? memberText(member) : task.name;
                      })()}</span>
                      <span className="flex gap-1">
                        <Button
                          size="small"
                          onClick={() => setCurrent({
                            ...current,
                            field_orders: (current.field_orders || []).map((item) => (
                              item.field === editingField ? { ...item, tasks: move(tasks, index, -1) } : item
                            )),
                          })}
                        >
                          {t('Collection.reconcileMoveUp')}
                        </Button>
                        <Button
                          size="small"
                          onClick={() => setCurrent({
                            ...current,
                            field_orders: (current.field_orders || []).map((item) => (
                              item.field === editingField ? { ...item, tasks: move(tasks, index, 1) } : item
                            )),
                          })}
                        >
                          {t('Collection.reconcileMoveDown')}
                        </Button>
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          </div>
          <Button
            type="primary"
            block
            loading={saving}
            disabled={draft && new Set(current.members.map((member) => member.model_id).filter(Boolean)).size > 1}
            onClick={draft ? createDraft : saveDetail}
          >
            {draft ? t('Collection.reconcileFinish') : t('Collection.reconcileSave')}
          </Button>
        </div>
      ) : null}
    </Drawer>
  );
};

export default ReconcileDrawer;
