'use client';

import React, { useMemo, useState } from 'react';
import { Button, Input, Modal, Select, Tag, Typography } from 'antd';
import { useTranslation } from '@/utils/i18n';

export interface EventBlockCatalog {
  max_rows: number;
  max_columns: number;
  default_limit: number;
  default_order: string;
  orders: Array<{ value: string; label: string }>;
  limits: Array<number | 'all'>;
  fields: Array<{ path: string; label: string }>;
  json_roots: Array<{ root: string; label: string }>;
}

const KEY_PATTERN = /^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$/;
const DEFAULT_PATHS = ['level', 'resource_name', 'item', 'value', 'start_time'];
const KEY_EXAMPLES: Record<string, string> = {
  tags: 'alert',
  labels: 'env',
  enrichment: 'cmdb.owner',
};

const BLOCK_PATTERN = /\{\{@\s*events\b[\s\S]*?@\}\}/g;

const headerFor = (path: string, labels: Record<string, string>) => labels[path] || path.replaceAll('.', '_');

const buildBlock = (
  columns: string[],
  labels: Record<string, string>,
  limit: string,
  order: string,
  headers: Record<string, string> = {},
) => {
  const expr = columns.map((path) => {
    const label = headers[path] || headerFor(path, labels);
    return label && label !== path ? `${path} as ${label}` : path;
  }).join(', ');
  return `{{@ events limit=${limit} order=${order} columns=${expr} @}}`;
};

const findEventBlocks = (source: string) => [...source.matchAll(BLOCK_PATTERN)].map((match) => match[0]);

const parseBlock = (raw: string) => {
  const text = raw.replace(/^\{\{@\s*/, '').replace(/\s*@\}\}$/, '').replace(/\s+/g, ' ').trim();
  if (!text.startsWith('events')) return null;
  const rest = text.slice('events'.length).trim();
  const matches = [...rest.matchAll(/(?:^|\s)([a-z_]+)=/g)];
  if (!matches.length) return null;
  const params: Record<string, string> = {};
  matches.forEach((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? (matches[index + 1].index ?? rest.length) : rest.length;
    params[match[1]] = rest.slice(start, end).trim();
  });
  if (!params.columns) return null;
  const columns: string[] = [];
  const headers: Record<string, string> = {};
  params.columns.split(',').map((item) => item.trim()).filter(Boolean).forEach((entry) => {
    const separator = entry.indexOf(' as ');
    const path = (separator === -1 ? entry : entry.slice(0, separator)).trim();
    const label = separator === -1 ? '' : entry.slice(separator + 4).trim();
    if (!path || columns.includes(path)) return;
    columns.push(path);
    if (label) headers[path] = label;
  });
  if (!columns.length) return null;
  return {
    limit: params.limit || '',
    order: params.order || '',
    columns,
    headers,
  };
};

interface EventBlockInsertProps {
  catalog: EventBlockCatalog;
  source: string;
  onApply: (text: string) => void;
}

export default function EventBlockInsert({ catalog, source, onApply }: EventBlockInsertProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [limit, setLimit] = useState(String(catalog.default_limit));
  const [order, setOrder] = useState(catalog.default_order);
  const [columns, setColumns] = useState<string[]>(
    DEFAULT_PATHS.filter((path) => catalog.fields.some((field) => field.path === path)),
  );
  const [openRoots, setOpenRoots] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [snippet, setSnippet] = useState('');
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const used = findEventBlocks(source).length > 0;

  const labels = useMemo(
    () => Object.fromEntries(catalog.fields.map((field) => [field.path, field.label])),
    [catalog.fields],
  );
  const columnLabel = (path: string) => headers[path] || headerFor(path, labels);
  const jsonRootsIn = (paths: string[]) => catalog.json_roots
    .map((item) => item.root)
    .filter((root) => paths.some((path) => path.startsWith(`${root}.`)));

  const writeSnippet = (
    nextColumns: string[],
    nextLimit: string,
    nextOrder: string,
    nextHeaders: Record<string, string> = headers,
  ) => {
    setSnippet(nextColumns.length ? buildBlock(nextColumns, labels, nextLimit, nextOrder, nextHeaders) : '');
  };

  const openModal = () => {
    const existing = findEventBlocks(source).at(-1);
    const parsed = existing ? parseBlock(existing) : null;
    if (parsed) {
      const nextLimit = parsed.limit || String(catalog.default_limit);
      const nextOrder = parsed.order || catalog.default_order;
      setColumns(parsed.columns);
      setLimit(nextLimit);
      setOrder(nextOrder);
      setHeaders(parsed.headers);
      setOpenRoots(jsonRootsIn(parsed.columns));
      writeSnippet(parsed.columns, nextLimit, nextOrder, parsed.headers);
    } else {
      const nextColumns = DEFAULT_PATHS.filter((path) => catalog.fields.some((field) => field.path === path));
      const nextLimit = String(catalog.default_limit);
      const nextOrder = catalog.default_order;
      setColumns(nextColumns);
      setLimit(nextLimit);
      setOrder(nextOrder);
      setOpenRoots([]);
      setHeaders({});
      writeSnippet(nextColumns, nextLimit, nextOrder, {});
    }
    setDrafts({});
    setError('');
    setOpen(true);
  };

  const toggleColumn = (path: string) => {
    setError('');
    setColumns((current) => {
      const next = current.includes(path)
        ? current.filter((item) => item !== path)
        : current.length >= catalog.max_columns
          ? current
          : [...current, path];
      if (!current.includes(path) && current.length >= catalog.max_columns) {
        setError(t('settings.notificationTemplate.eventBlockMaxColumns', undefined, { count: catalog.max_columns }));
      }
      if (next !== current) {
        const nextHeaders = { ...headers };
        current.filter((item) => !next.includes(item)).forEach((item) => delete nextHeaders[item]);
        setHeaders(nextHeaders);
        writeSnippet(next, limit, order, nextHeaders);
      }
      return next;
    });
  };

  const addNested = (root: string) => {
    const key = (drafts[root] || '').trim().replace(/^\.+|\.+$/g, '');
    if (!key) return;
    if (!KEY_PATTERN.test(key)) {
      setError(t('settings.notificationTemplate.eventBlockKeyInvalid'));
      return;
    }
    const path = `${root}.${key}`;
    if (path.split('.').length > 4) {
      setError(t('settings.notificationTemplate.eventBlockKeyTooDeep'));
      return;
    }
    if (columns.includes(path)) {
      setError(t('settings.notificationTemplate.eventBlockDuplicate'));
      return;
    }
    if (columns.length >= catalog.max_columns) {
      setError(t('settings.notificationTemplate.eventBlockMaxColumns', undefined, { count: catalog.max_columns }));
      return;
    }
    setError('');
    const next = [...columns, path];
    setColumns(next);
    setOpenRoots((current) => current.includes(root) ? current : [...current, root]);
    writeSnippet(next, limit, order);
    setDrafts((current) => ({ ...current, [root]: '' }));
  };

  const changeLimit = (value: string) => {
    setLimit(value);
    writeSnippet(columns, value, order);
  };

  const changeOrder = (value: string) => {
    setOrder(value);
    writeSnippet(columns, limit, value);
  };

  const editSnippet = (value: string) => {
    setSnippet(value);
    const parsed = parseBlock(value);
    if (!parsed) return;
    setColumns(parsed.columns);
    setHeaders(parsed.headers);
    if (parsed.limit) setLimit(parsed.limit);
    if (parsed.order) setOrder(parsed.order);
    setOpenRoots(jsonRootsIn(parsed.columns));
    setError('');
  };

  return (
    <>
      <Button
        size="small"
        type={used ? 'primary' : 'dashed'}
        ghost={used}
        onClick={openModal}
      >
        {t('settings.notificationTemplate.insertEventBlock')}
      </Button>
      <Modal
        title={t('settings.notificationTemplate.eventBlockTitle')}
        open={open}
        okText={t('settings.notificationTemplate.insertEventBlock')}
        cancelText={t('common.cancel')}
        okButtonProps={{ disabled: !snippet.trim() }}
        onOk={() => {
          onApply(snippet.trim());
          setOpen(false);
        }}
        onCancel={() => setOpen(false)}
        width={680}
      >
        <Typography.Paragraph type="secondary" className="!mb-4">
          {t('settings.notificationTemplate.eventBlockHint')}
        </Typography.Paragraph>
        <div className="mb-4 grid grid-cols-2 gap-3">
          <div>
            <Typography.Text>{t('settings.notificationTemplate.eventBlockLimit')}</Typography.Text>
            <Select
              className="mt-1 w-full"
              value={limit}
              options={catalog.limits.map((item) => ({
                value: String(item),
                label: item === 'all'
                  ? t('settings.notificationTemplate.eventBlockAll', undefined, { count: catalog.max_rows })
                  : String(item),
              }))}
              onChange={changeLimit}
            />
          </div>
          <div>
            <Typography.Text>{t('settings.notificationTemplate.eventBlockOrder')}</Typography.Text>
            <Select
              className="mt-1 w-full"
              value={order}
              options={catalog.orders.map((item) => ({ value: item.value, label: item.label }))}
              onChange={changeOrder}
            />
          </div>
        </div>
        <Typography.Text>
          {t('settings.notificationTemplate.eventBlockColumns', undefined, { count: catalog.max_columns })}
        </Typography.Text>
        <div className="mt-2 flex min-h-10 flex-wrap gap-2 rounded border border-[var(--color-border-2)] p-2">
          {columns.length === 0 && (
            <Typography.Text type="secondary">{t('settings.notificationTemplate.eventBlockEmptyColumns')}</Typography.Text>
          )}
          {columns.map((path) => (
            <Tag key={path} closable onClose={() => toggleColumn(path)}>
              {columnLabel(path)} · {path}
            </Tag>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {catalog.fields.map((field) => (
            <Button
              key={field.path}
              size="small"
              type={columns.includes(field.path) ? 'primary' : 'default'}
              ghost={columns.includes(field.path)}
              onClick={() => toggleColumn(field.path)}
            >
              {field.label}
            </Button>
          ))}
        </div>
        <Typography.Text className="mt-4 block">{t('settings.notificationTemplate.eventBlockJson')}</Typography.Text>
        <Typography.Paragraph type="secondary" className="!mb-2">
          {t('settings.notificationTemplate.eventBlockJsonHint')}
        </Typography.Paragraph>
        <div className="flex flex-wrap gap-2">
          {catalog.json_roots.map((item) => {
            const added = columns.filter((path) => path.startsWith(`${item.root}.`)).length;
            return (
              <Button
                key={item.root}
                size="small"
                type={openRoots.includes(item.root) || added > 0 ? 'primary' : 'default'}
                ghost={openRoots.includes(item.root) || added > 0}
                onClick={() => setOpenRoots((current) => (
                  current.includes(item.root) ? current.filter((root) => root !== item.root) : [...current, item.root]
                ))}
              >
                {item.label} {item.root}
                {added > 0 ? ` · ${t('settings.notificationTemplate.eventBlockAdded', undefined, { count: added })}` : ''}
              </Button>
            );
          })}
        </div>
        {catalog.json_roots.filter((item) => openRoots.includes(item.root)).map((item) => (
          <div key={item.root} className="mt-3 flex items-center gap-2">
            <Tag>{item.root}.</Tag>
            <Input
              value={drafts[item.root] || ''}
              placeholder={t('settings.notificationTemplate.eventBlockKeyPlaceholder', undefined, { example: KEY_EXAMPLES[item.root] || 'key' })}
              onChange={(event) => setDrafts((current) => ({ ...current, [item.root]: event.target.value }))}
              onPressEnter={() => addNested(item.root)}
            />
            <Button onClick={() => addNested(item.root)}>{t('settings.notificationTemplate.eventBlockAdd')}</Button>
          </div>
        ))}
        {error && <Typography.Text type="danger" className="mt-2 block">{error}</Typography.Text>}
        <Typography.Text className="mt-4 block">{t('settings.notificationTemplate.eventBlockWillInsert')}</Typography.Text>
        <Input.TextArea
          className="mt-1"
          value={snippet}
          autoSize={{ minRows: 2, maxRows: 6 }}
          onChange={(event) => editSnippet(event.target.value)}
        />
      </Modal>
    </>
  );
}
