'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Modal, Select, Table, Tabs } from 'antd';
import TopSection from '@/components/top-section';
import { useTranslation } from '@/utils/i18n';
import {
  HandoverFailure,
  HandoverModel,
  HandoverPreview,
  HandoverTask,
  HandoverUser,
  useOwnerHandoverApi,
} from '@/app/cmdb/api';

const ACTIVE = new Set(['queued', 'running']);
const CLEANUP_DAYS = [7, 30, 90, 180, 365];
const TRANSFER_STATUS_CLASS: Record<string, string> = {
  pending: 'text-[var(--color-text-3)]',
  succeeded: 'text-[var(--color-success)]',
  failed: 'text-[var(--color-fail)]',
};
const TRANSFER_STATUS_TEXT: Record<string, string> = {
  pending: 'OwnerHandover.transferPending',
  succeeded: 'OwnerHandover.transferSucceeded',
  failed: 'OwnerHandover.transferFailed',
};

const TASK_STATUS_TEXT: Record<string, string> = {
  queued: 'OwnerHandover.queued',
  running: 'OwnerHandover.running',
  succeeded: 'OwnerHandover.transferSucceeded',
  partial_failed: 'OwnerHandover.partialStatus',
  failed: 'OwnerHandover.failed',
  cancelled: 'OwnerHandover.cancelledStatus',
};

const formatTaskTime = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const HistoryPanel: React.FC<{ active: boolean }> = ({ active }) => {
  const { t } = useTranslation();
  const api = useOwnerHandoverApi();
  const [userId, setUserId] = useState<number>();
  const [options, setOptions] = useState<HandoverUser[]>([]);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<HandoverTask[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = async (nextPage = page, nextUser = userId) => {
    setLoading(true);
    setError('');
    try {
      const result = await api.listTasks(nextUser, nextPage, 20);
      setRows(result.items);
      setTotal(result.count);
    } catch (err) {
      const text = (err as { response?: { data?: { message?: string } } })?.response?.data?.message;
      setError(text || t('OwnerHandover.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (active) load(page, userId);
  }, [active, page, userId]);

  const onDelete = () => {
    if (!selected.length) return;
    Modal.confirm({
      title: t('OwnerHandover.historyDeleteTitle'),
      content: t('OwnerHandover.historyDeleteConfirm', '', { count: selected.length }),
      okText: t('OwnerHandover.historyDelete'),
      cancelText: t('OwnerHandover.cleanupCancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        setError('');
        try {
          const result = await api.deleteTasks(selected);
          setSelected([]);
          setMessage(t('OwnerHandover.historyDeleted', '', { deleted: result.deleted, kept: result.kept }));
          await load(page, userId);
        } catch (err) {
          const text = (err as { response?: { data?: { message?: string } } })?.response?.data?.message;
          setError(text || t('OwnerHandover.loadFailed'));
        }
      },
    });
  };

  return (
    <div className="rounded-md bg-[var(--color-bg)] p-4">
      <div className="mb-4 flex flex-wrap items-end justify-end gap-2">
        <Select
          allowClear
          showSearch
          filterOption={false}
          className="w-64"
          value={userId}
          placeholder={t('OwnerHandover.historyUserPlaceholder')}
          options={options.map((item) => ({ value: item.id, label: item.label }))}
          onSearch={async (search) => setOptions(await api.searchUsers('from', search))}
          onFocus={() => api.searchUsers('from', '').then(setOptions)}
          onChange={(value) => {
            setUserId(value);
            setPage(1);
            setSelected([]);
          }}
        />
        <Button danger disabled={!selected.length} onClick={onDelete}>
          {t('OwnerHandover.historyDelete')}
        </Button>
      </div>
      {error ? <Alert className="mb-4" type="error" showIcon message={error} /> : null}
      {message ? <Alert className="mb-4" type="success" showIcon message={message} /> : null}
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={rows}
        locale={{ emptyText: t('OwnerHandover.historyEmpty') }}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys.map(String)),
          getCheckboxProps: (row) => ({ disabled: ACTIVE.has(row.status) }),
        }}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          { title: t('OwnerHandover.historyTime'), dataIndex: 'created_at', render: formatTaskTime },
          { title: t('OwnerHandover.from'), dataIndex: 'from_label' },
          { title: t('OwnerHandover.to'), dataIndex: 'to_label' },
          { title: t('OwnerHandover.field'), dataIndex: 'attr_name' },
          {
            title: t('OwnerHandover.transferStatus'),
            dataIndex: 'status',
            render: (status: string) => t(TASK_STATUS_TEXT[status] || 'OwnerHandover.failed'),
          },
          {
            title: t('OwnerHandover.historyResult'),
            render: (_value, row) =>
              t('OwnerHandover.historyCounts', '', { success: row.success_count, failed: row.failed_count }),
          },
        ]}
      />
    </div>
  );
};

const CleanupPanel: React.FC = () => {
  const { t } = useTranslation();
  const api = useOwnerHandoverApi();
  const [cleanupUsers, setCleanupUsers] = useState<number[]>([]);
  const [cleanupDays, setCleanupDays] = useState<number>(30);
  const [cleanupOptions, setCleanupOptions] = useState<HandoverUser[]>([]);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState('');
  const [error, setError] = useState('');

  return (
    <div className="rounded-md bg-[var(--color-bg)] p-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex w-full max-w-md flex-col gap-2 text-sm">
          {t('OwnerHandover.cleanupUser')}
          <Select
            className="w-full"
            mode="multiple"
            allowClear
            showSearch
            filterOption={false}
            maxTagCount="responsive"
            value={cleanupUsers}
            placeholder={t('OwnerHandover.cleanupUserPlaceholder')}
            options={cleanupOptions.map((item) => ({ value: item.id, label: item.label }))}
            onSearch={async (search) => {
              const rows = await api.searchUsers('from', search);
              setCleanupOptions((current) => {
                const merged = new Map(current.map((item) => [item.id, item]));
                rows.forEach((item) => merged.set(item.id, item));
                return [...merged.values()];
              });
            }}
            onFocus={() =>
              api.searchUsers('from', '').then((rows) =>
                setCleanupOptions((current) => {
                  const merged = new Map(rows.map((item) => [item.id, item]));
                  current.forEach((item) => {
                    if (cleanupUsers.includes(item.id)) merged.set(item.id, item);
                  });
                  return [...merged.values()];
                })
              )
            }
            onChange={setCleanupUsers}
          />
        </label>
        <label className="flex w-36 flex-col gap-2 text-sm">
          {t('OwnerHandover.cleanupDays')}
          <Select
            className="w-full"
            value={cleanupDays}
            options={CLEANUP_DAYS.map((days) => ({
              value: days,
              label: t('OwnerHandover.cleanupDaysOption', '', { days }),
            }))}
            onChange={setCleanupDays}
          />
        </label>
        <Button
          danger
          loading={cleaning}
          onClick={() => {
            const labels = cleanupUsers
              .map((userId) => cleanupOptions.find((item) => item.id === userId)?.label || String(userId))
              .join('、');
            Modal.confirm({
              title: t('OwnerHandover.cleanupConfirmTitle'),
              content: cleanupUsers.length
                ? t('OwnerHandover.cleanupConfirm', '', {
                  user: labels,
                  days: cleanupDays,
                })
                : t('OwnerHandover.cleanupConfirmAll', '', { days: cleanupDays }),
              okText: t('OwnerHandover.cleanupAction'),
              cancelText: t('OwnerHandover.cleanupCancel'),
              okButtonProps: { danger: true },
              onOk: async () => {
                setCleaning(true);
                setError('');
                try {
                  const result = await api.cleanupHistory(cleanupUsers, cleanupDays);
                  setCleanupMessage(
                    t('OwnerHandover.cleanupDone', '', { tasks: result.tasks, records: result.records })
                  );
                } catch (err) {
                  const text = (err as { response?: { data?: { message?: string } } })?.response?.data?.message;
                  setError(text || t('OwnerHandover.loadFailed'));
                } finally {
                  setCleaning(false);
                }
              },
            });
          }}
        >
          {t('OwnerHandover.cleanupAction')}
        </Button>
      </div>
      {error ? <Alert className="mt-4" type="error" showIcon message={error} /> : null}
      {cleanupMessage ? <Alert className="mt-4" type="success" showIcon message={cleanupMessage} /> : null}
    </div>
  );
};

const OwnerHandoverPage: React.FC = () => {
  const { t } = useTranslation();
  const api = useOwnerHandoverApi();
  const [models, setModels] = useState<HandoverModel[]>([]);
  const [fromUser, setFromUser] = useState<number | undefined>();
  const [toUser, setToUser] = useState<number | undefined>();
  const [fromOptions, setFromOptions] = useState<HandoverUser[]>([]);
  const [toOptions, setToOptions] = useState<HandoverUser[]>([]);
  const [allModels, setAllModels] = useState(true);
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [fieldKey, setFieldKey] = useState<string>();
  const [preview, setPreview] = useState<HandoverPreview | null>(null);
  const previewRef = useRef(preview);
  previewRef.current = preview;
  const [previewKey, setPreviewKey] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [task, setTask] = useState<HandoverTask | null>(null);
  const [failures, setFailures] = useState<HandoverFailure[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('transfer');

  const errorText = (err: unknown) => {
    const message = (err as { response?: { data?: { message?: string } } })?.response?.data?.message;
    return message || t('OwnerHandover.loadFailed');
  };

  useEffect(() => {
    api.getModels().then(setModels).catch(() => setModels([]));
  }, []);

  const fieldOptions = useMemo(() => {
    const seen = new Map<string, { attr_id: string; attr_name: string }>();
    models.forEach((model) => {
      model.fields.forEach((field) => {
        seen.set(`${field.attr_id}\n${field.attr_name}`, field);
      });
    });
    const fields = [...seen.values()].sort((left, right) => left.attr_name.localeCompare(right.attr_name, 'zh'));
    const nameCount = new Map<string, number>();
    fields.forEach((field) => nameCount.set(field.attr_name, (nameCount.get(field.attr_name) || 0) + 1));
    return fields.map((field) => ({
      ...field,
      label: (nameCount.get(field.attr_name) || 0) > 1 ? `${field.attr_name} (${field.attr_id})` : field.attr_name,
    }));
  }, [models]);
  const selectedField = fieldOptions.find((field) => `${field.attr_id}\n${field.attr_name}` === fieldKey);
  const visibleModels = useMemo(
    () =>
      selectedField
        ? models.filter((model) =>
          model.fields.some(
            (field) => field.attr_id === selectedField.attr_id && field.attr_name === selectedField.attr_name
          )
        )
        : [],
    [models, selectedField]
  );
  const selectedModels = allModels
    ? visibleModels.map((item) => item.model_id)
    : modelIds.filter((modelId) => visibleModels.some((model) => model.model_id === modelId));
  const formKey = `${fromUser || ''}:${toUser || ''}:${fieldKey || ''}:${selectedModels.join(',')}`;
  const previewReady = Boolean(preview && previewKey === formKey && fromUser !== toUser);

  const searchUsers = async (role: 'from' | 'to', search: string) => {
    const rows = await api.searchUsers(role, search);
    if (role === 'from') setFromOptions(rows);
    else setToOptions(rows);
  };

  const onPreview = async () => {
    if (!fromUser || !toUser || fromUser === toUser || !selectedField) return;
    setLoading(true);
    setError('');
    setTask(null);
    setFailures([]);
    try {
      const result = await api.preview({
        from_user_id: fromUser,
        to_user_id: toUser,
        attr_id: selectedField.attr_id,
        attr_name: selectedField.attr_name,
        model_ids: allModels ? undefined : selectedModels,
        page: 1,
        page_size: 50,
      });
      setPreview(result);
      setPreviewKey(formKey);
      setIdempotencyKey(crypto.randomUUID());
    } catch (err) {
      setPreview(null);
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  };

  const onCancel = async () => {
    if (!task || !ACTIVE.has(task.status)) return;
    setRunning(true);
    setError('');
    try {
      setTask(await api.cancelTask(task.id));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setRunning(false);
    }
  };

  const onExecute = async () => {
    if (!preview || !previewReady) return;
    setRunning(true);
    setError('');
    try {
      const created = await api.createTask(preview.preview_token, idempotencyKey);
      setTask(created);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (!task || !ACTIVE.has(task.status)) return undefined;
    const timer = window.setInterval(async () => {
      const latest = await api.getTask(task.id);
      setTask(latest);
      if (!ACTIVE.has(latest.status) && latest.failed_count > 0) {
        const page = await api.getFailures(task.id);
        setFailures(page.items);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [task?.id, task?.status]);

  useEffect(() => {
    if (!task || ACTIVE.has(task.status)) return undefined;
    const items = previewRef.current?.items ?? [];
    if (!items.length) return undefined;
    let cancelled = false;
    api
      .getOutcomes(
        task.id,
        items.map((item) => item.inst_uuid)
      )
      .then((rows) => {
        if (cancelled) return;
        const byUuid = new Map(rows.map((row) => [row.inst_uuid, row.transfer_status]));
        setPreview((current) =>
          current
            ? {
              ...current,
              items: current.items.map((item) => ({
                ...item,
                transfer_status: byUuid.get(item.inst_uuid) || 'pending',
              })),
            }
            : current
        );
      })
      .catch((err) => {
        if (!cancelled) setError(errorText(err));
      });
    return () => {
      cancelled = true;
    };
  }, [task?.id, task?.status]);

  const distribution = useMemo(() => {
    if (!preview) return '';
    return preview.by_model.map((item) => `${item.model_name} ${item.count}`).join('，');
  }, [preview]);

  const columns = [
    { title: t('OwnerHandover.model'), dataIndex: 'model_name' },
    { title: t('OwnerHandover.instance'), dataIndex: 'inst_name' },
    { title: t('OwnerHandover.organization'), dataIndex: 'organization' },
    {
      title: t('OwnerHandover.owner'),
      dataIndex: 'changes',
      render: (changes: HandoverPreview['items'][number]['changes']) =>
        changes.map((item) => `${item.attr_name} ${item.before} → ${item.after}`).join('；'),
    },
    {
      title: t('OwnerHandover.transferStatus'),
      dataIndex: 'transfer_status',
      render: (status: string) => {
        const value = TRANSFER_STATUS_TEXT[status] ? status : 'pending';
        return <span className={TRANSFER_STATUS_CLASS[value]}>{t(TRANSFER_STATUS_TEXT[value])}</span>;
      },
    },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <TopSection title={t('OwnerHandover.title')} content={t('OwnerHandover.description')} />
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: 'transfer', label: t('OwnerHandover.tabTransfer'), children: <div className="rounded-md bg-[var(--color-bg)] p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm">
            {t('OwnerHandover.field')}
            <Select
              showSearch
              optionFilterProp="label"
              value={fieldKey}
              placeholder={t('OwnerHandover.fieldPlaceholder')}
              options={fieldOptions.map((field) => ({
                value: `${field.attr_id}\n${field.attr_name}`,
                label: field.label,
              }))}
              onChange={(value) => {
                setFieldKey(value);
                setAllModels(true);
                setModelIds([]);
                setPreview(null);
              }}
            />
          </label>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm">
            {t('OwnerHandover.from')}
            <Select
              showSearch
              filterOption={false}
              value={fromUser}
              placeholder={t('OwnerHandover.fromPlaceholder')}
              options={fromOptions.map((item) => ({ value: item.id, label: item.label }))}
              onSearch={(value) => searchUsers('from', value)}
              onFocus={() => searchUsers('from', '')}
              onChange={(value) => {
                setFromUser(value);
                setPreview(null);
              }}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm">
            {t('OwnerHandover.to')}
            <Select
              showSearch
              filterOption={false}
              value={toUser}
              placeholder={t('OwnerHandover.toPlaceholder')}
              options={toOptions.map((item) => ({ value: item.id, label: item.label }))}
              onSearch={(value) => searchUsers('to', value)}
              onFocus={() => searchUsers('to', '')}
              onChange={(value) => {
                setToUser(value);
                setPreview(null);
              }}
            />
          </label>
        </div>
        <fieldset className="mt-4 border-0 p-0">
          <legend className="mb-2 text-sm">{t('OwnerHandover.models')}</legend>
          {selectedField ? (
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              <Checkbox
                checked={allModels}
                onChange={(event) => {
                  setAllModels(event.target.checked);
                  setPreview(null);
                }}
              >
                {t('OwnerHandover.allModels')}
              </Checkbox>
              {visibleModels.map((model) => (
                <Checkbox
                  key={model.model_id}
                  checked={allModels || modelIds.includes(model.model_id)}
                  disabled={allModels}
                  onChange={(event) => {
                    setModelIds((current) =>
                      event.target.checked
                        ? [...current, model.model_id]
                        : current.filter((item) => item !== model.model_id)
                    );
                    setPreview(null);
                  }}
                >
                  {model.model_name}
                </Checkbox>
              ))}
            </div>
          ) : (
            <span className="text-sm text-[var(--color-text-3)]">{t('OwnerHandover.fieldPlaceholder')}</span>
          )}
        </fieldset>
        <Alert className="mt-4" type="warning" showIcon message={t('OwnerHandover.note')} />
        {error ? <Alert className="mt-4" type="error" showIcon message={error} /> : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            onClick={onPreview}
            loading={loading}
            disabled={
              !fromUser ||
              !toUser ||
              !selectedField ||
              fromUser === toUser ||
              (!allModels && selectedModels.length === 0)
            }
          >
            {t('OwnerHandover.preview')}
          </Button>
          <Button type="primary" onClick={onExecute} loading={running} disabled={!previewReady || preview?.total === 0}>
            {t('OwnerHandover.execute')}
          </Button>
          {task && ACTIVE.has(task.status) ? (
            <Button onClick={onCancel} disabled={running}>
              {t('OwnerHandover.cancel')}
            </Button>
          ) : null}
        </div>
        {fromUser && toUser && fromUser === toUser ? (
          <Alert className="mt-4" type="error" showIcon message={t('OwnerHandover.sameUser')} />
        ) : null}
        {preview && previewKey === formKey ? (
          <div className="mt-4">
            <h3 className="mb-2 text-sm font-medium">{t('OwnerHandover.willChange')}</h3>
            <p className="mb-2 text-xs text-[var(--color-text-3)]">
              {t('OwnerHandover.count', '', { total: preview.total })}
              {distribution ? `：${distribution}` : ''}
              {preview.excluded_no_permission
                ? `。${t('OwnerHandover.excluded', '', { count: preview.excluded_no_permission })}`
                : ''}
            </p>
            <Table
              rowKey="inst_uuid"
              size="small"
              pagination={false}
              columns={columns}
              dataSource={preview.items}
              locale={{ emptyText: t('OwnerHandover.empty') }}
            />
          </div>
        ) : null}
        {task && task.status === 'succeeded' ? (
          <Alert
            className="mt-4"
            type="success"
            showIcon
            message={t('OwnerHandover.success', '', {
              success: task.success_count,
              from: task.from_label,
              to: task.to_label,
            })}
          />
        ) : null}
        {task && task.status === 'partial_failed' ? (
          <Alert
            className="mt-4"
            type="warning"
            showIcon
            message={t('OwnerHandover.partial', '', { success: task.success_count, failed: task.failed_count })}
          />
        ) : null}
        {task && task.status === 'failed' ? (
          <Alert className="mt-4" type="error" showIcon message={task.message || t('OwnerHandover.failed')} />
        ) : null}
        {task && task.status === 'cancelled' ? (
          <Alert className="mt-4" type="warning" showIcon message={t('OwnerHandover.cancelled')} />
        ) : null}
        {task && ACTIVE.has(task.status) ? (
          <Alert className="mt-4" type="info" showIcon message={t('OwnerHandover.running')} />
        ) : null}
        {failures.length ? (
          <div className="mt-4">
            <h3 className="mb-2 text-sm font-medium">{t('OwnerHandover.failures')}</h3>
            <Table
              rowKey={(row) => `${row.model_name}-${row.inst_name}`}
              size="small"
              pagination={false}
              dataSource={failures}
              columns={[
                { title: t('OwnerHandover.model'), dataIndex: 'model_name' },
                { title: t('OwnerHandover.instance'), dataIndex: 'inst_name' },
                { title: t('OwnerHandover.reason'), dataIndex: 'message' },
              ]}
            />
          </div>
        ) : null}
      </div> },
          { key: 'history', label: t('OwnerHandover.tabHistory'), children: <HistoryPanel active={tab === 'history'} /> },
          { key: 'cleanup', label: t('OwnerHandover.tabCleanup'), children: <CleanupPanel /> },
        ]}
      />
    </div>
  );
};

export default OwnerHandoverPage;
