'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Alert, App, Button, Empty, Input, Popconfirm, Popover, Select, Spin, Tag, Tooltip } from 'antd';
import { CopyOutlined, StarFilled, StarOutlined, TagsOutlined } from '@ant-design/icons';
import { useItsmApi } from '../api/useItsmApi';

interface TagsData { items: { id: number; name: string; color?: string }[]; can_manage: boolean }
interface FollowData { items: string[]; following: boolean }
interface Relation { id: number; related_id: number; related_sn: string; related_title: string; relation_type: string; can_remove: boolean }
interface RelationsData { items: Relation[]; can_manage: boolean }
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失败，请重试';

const TAG_COLORS = ['#1677ff', '#13c2c2', '#52c41a', '#faad14', '#fa8c16', '#f5222d', '#eb2f96', '#722ed1'];

export function TicketHeaderSocial({ ticketId, sn }: { ticketId: number; sn?: string }) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [followers, setFollowers] = useState<FollowData>({ items: [], following: false });
  const [tags, setTags] = useState<TagsData>({ items: [], can_manage: false });
  const [name, setName] = useState('');
  const [color, setColor] = useState(TAG_COLORS[0]);
  const [tagOpen, setTagOpen] = useState(false);
  const [choices, setChoices] = useState<{ name: string; color?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const [followData, tagData] = await Promise.all([api.listFollowers(ticketId), api.listTags(ticketId)]);
    setFollowers(followData as FollowData); setTags(tagData as TagsData); setLoaded(true); setError('');
  }, [api.listFollowers, api.listTags, ticketId]);
  useEffect(() => { if (api.ready) void load().catch((e: unknown) => setError(errorText(e))); }, [api.ready, load]);
  useEffect(() => {
    if (!tagOpen) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void api.searchTicketTags(name).then(value => { if (active) setChoices((value as { items: { name: string; color?: string }[] }).items); })
        .catch((e: unknown) => { if (active) message.error(errorText(e)); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [tagOpen, name, api.searchTicketTags, message]);
  const mutate = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    try { await operation(); await load(); } catch (e) { message.error(errorText(e)); } finally { setBusy(false); }
  };
  if (error) return <Alert type="error" message={error} action={<Button onClick={() => void load().catch((e: unknown) => setError(errorText(e)))}>重试</Button>} />;
  if (!loaded) return <Spin />;
  return <div className="flex flex-wrap items-center gap-2">
    <div className="flex items-center gap-1" role="group" aria-label="工单快捷操作">
      {sn ? <CopyTicketNumber sn={sn} /> : null}
      <Tooltip title={followers.following ? '取消关注' : '关注工单'}><Button size="small" type="text" aria-label={followers.following ? '取消关注' : '关注工单'} aria-pressed={followers.following} loading={busy} icon={followers.following ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />} onClick={() => void mutate(() => api.toggleFollow(ticketId, !followers.following))} /></Tooltip>
      {tags.can_manage ? <Popover trigger="click" open={tagOpen} onOpenChange={setTagOpen} title="工单标签" content={<div className="flex w-72 flex-col gap-3">
        <Select aria-label="选择已有标签" showSearch filterOption={false} placeholder="搜索并选择已有标签" onSearch={setName} value={undefined} disabled={busy} options={choices.filter(item => !tags.items.some(tag => tag.name === item.name)).map(item => ({ value: item.name, label: <Tag color={item.color || '#1677ff'}>{item.name}</Tag> }))} onChange={value => void mutate(() => api.addTag(ticketId, value))} />
        <Input aria-label="标签名称" placeholder="新标签名称" maxLength={64} value={name} onChange={event => setName(event.target.value)} />
        <div role="group" aria-label="推荐配色" className="flex gap-2">{TAG_COLORS.map(value => <button key={value} type="button" aria-label={`配色 ${value}`} aria-pressed={color === value} onClick={() => setColor(value)} className="h-6 w-6 rounded-full border-2 border-white outline-offset-2 focus-visible:outline" style={{ backgroundColor: value, outline: color === value ? `2px solid ${value}` : undefined }} />)}</div>
        <Tag className="w-fit" color={color}>{name.trim() || '标签预览'}</Tag>
        <Button loading={busy} disabled={!name.trim()} onClick={() => void mutate(async () => { await api.addTag(ticketId, name.trim(), color); setName(''); })}>添加</Button>
      </div>}><Tooltip title="标签"><Button type="text" size="small" aria-label="标签" icon={<TagsOutlined />} /></Tooltip></Popover> : null}
    </div>
    {tags.items.map(tag => <span key={tag.id} className="group inline-flex items-center gap-1"><Tag className="!m-0" color={tag.color || '#1677ff'}>{tag.name}</Tag>{tags.can_manage ? <Popconfirm title={`移除标签“${tag.name}”？`} description="仅移除此工单的标签。" onConfirm={() => mutate(() => api.removeTag(ticketId, tag.id))}><Button className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100" size="small" type="text" disabled={busy} aria-label={`移除标签 ${tag.name}`}>×</Button></Popconfirm> : null}</span>)}
  </div>;
}

export function CopyTicketNumber({ sn }: { sn: string }) {
  const { message } = App.useApp();
  return <Tooltip title="复制单号"><Button type="text" size="small" aria-label="复制单号" icon={<CopyOutlined />} onClick={() => {
    void navigator.clipboard.writeText(sn).then(() => message.success('单号已复制')).catch(() => message.error('复制失败，请手动复制单号'));
  }} /></Tooltip>;

}

export function TicketRelations({ ticketId }: { ticketId: number }) {
  const api = useItsmApi();
  const { message } = App.useApp();
  const [data, setData] = useState<RelationsData>({ items: [], can_manage: false });
  const [keyword, setKeyword] = useState('');
  const [options, setOptions] = useState<{ value: number; label: string; sn: string; title: string }[]>([]);
  const [selected, setSelected] = useState<number>();
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => { setData(await api.listRelations(ticketId) as RelationsData); setLoaded(true); setError(''); }, [api.listRelations, ticketId]);
  useEffect(() => { if (api.ready) void load().catch((e: unknown) => setError(errorText(e))); }, [api.ready, load]);
  useEffect(() => {
    if (!data.can_manage || !api.ready) return;
    let active = true;
    setSearching(true);
    const timer = window.setTimeout(() => {
      void api.listTickets({ q: keyword, relation_for: ticketId, page_size: 20 }).then((result) => {
        if (active) setOptions((result.items as { id: number; sn: string; title: string }[]).map((item) => ({ value: item.id, label: `${item.sn} · ${item.title}`, sn: item.sn, title: item.title })));
      }).catch((e: unknown) => { if (active) { setOptions([]); message.error(errorText(e)); } }).finally(() => { if (active) setSearching(false); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [api.ready, api.listTickets, keyword, ticketId, data, message]);
  const mutate = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    try { await operation(); setSelected(undefined); await load(); } catch (e) { message.error(errorText(e)); } finally { setBusy(false); }
  };
  if (error) return <Alert type="error" message={error} action={<Button onClick={() => void load().catch((e: unknown) => setError(errorText(e)))}>重试</Button>} />;
  if (!loaded) return <Spin />;
  return <div className="flex flex-col gap-4 py-2">
    {data.can_manage ? <div className="flex flex-col gap-2"><span className="text-sm font-medium">添加关联单</span><Select aria-label="搜索关联工单" showSearch filterOption={false} placeholder="按单号或标题搜索" searchValue={keyword} onSearch={setKeyword} loading={searching} value={selected} onChange={setSelected} options={options} virtual={false} optionRender={(option) => <div className="flex flex-col gap-1 py-1"><span className="whitespace-normal break-words text-sm">{option.data.title}</span><span className="text-xs text-[var(--color-text-3)]">{option.data.sn}</span></div>} notFoundContent={searching ? <Spin size="small" /> : '没有可关联的工单'} className="w-full" /><Button disabled={!selected} loading={busy} onClick={() => selected && void mutate(() => api.addRelation(ticketId, selected))}>建立关联</Button></div> : null}
    {data.items.length ? data.items.map((item) => <div key={item.id} className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3"><Link href={`/itsm/tickets/${item.related_id}`} className="break-words text-sm text-[var(--color-primary)]">{item.related_sn}<span className="mt-1 block text-[var(--color-text-1)]">{item.related_title}</span></Link><div className="flex items-center justify-between"><Tag>{item.relation_type === 'related' ? '关联工单' : item.relation_type === 'child' ? '子流程关联' : '业务关联'}</Tag>{item.can_remove ? <Popconfirm title="解除这两张工单的关联？" description="两端同时解除，不删除工单。" onConfirm={() => mutate(() => api.removeRelation(ticketId, item.id))}><Button size="small" type="text" danger disabled={busy}>解除关联</Button></Popconfirm> : null}</div></div>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关联工单" />}
  </div>;
}
