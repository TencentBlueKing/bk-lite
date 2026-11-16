import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { App } from 'antd';
import PortalPage from './page';
const api = vi.hoisted(() => ({ ready: true, portal: vi.fn(), portalLayout: vi.fn(), portalDashboard: vi.fn(), savePortalLayout: vi.fn(), toggleFavorite: vi.fn() }));
vi.mock('../api/useItsmApi', () => ({ useItsmApi: () => api }));
vi.mock('next/link', () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }) });
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  api.portal.mockResolvedValue({ can_manage: true, can_apply: true, catalogs: [{ id: 1, name: '办公服务', parent_id: null }, { id: 2, name: '设备', parent_id: 1 }], services: [{ id: 1, name: '电脑申请', description: '办公电脑', catalog_id: 2 }, { id: 2, name: '网络申请', catalog_id: null }], favorites: [], recents: [], hots: [] });
  api.portalLayout.mockResolvedValue({ title: '团队服务台', subtitle: '欢迎使用', background: 'blue', widgets: [{ type: 'services', width: 12 }] });
  api.portalDashboard.mockResolvedValue({ stats: { total: 0, todo: 0, finished: 0, active: 0 }, tickets: [], todo: [], trend: [], announcements: [] });
});
it('服务支持搜索、收藏与申请入口', async () => {
  render(<App><PortalPage /></App>);
  expect((await screen.findByRole('link', { name: /电脑申请/ })).getAttribute('href')).toBe('/itsm/tickets/new?service_id=1');
  fireEvent.change(screen.getByRole('textbox', { name: '搜索服务' }), { target: { value: '电脑' } });
  expect(screen.queryByRole('link', { name: /网络申请/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '收藏电脑申请' }));
  await waitFor(() => expect(api.toggleFavorite).toHaveBeenCalledWith(1));
});
it('普通用户没有配置入口', async () => {
  api.portal.mockResolvedValue({ can_manage: false, can_apply: false, catalogs: [], services: [], favorites: [], recents: [], hots: [] });
  render(<App><PortalPage /></App>);
  await screen.findByText('团队服务台');
  expect(screen.queryByRole('button', { name: /编排门户/ })).toBeNull();
  expect(screen.queryByRole('link', { name: /管理服务/ })).toBeNull();
});
it('编辑布局取消不会保存，发布提交新标题', async () => {
  api.savePortalLayout.mockImplementation(async value => value);
  render(<App><PortalPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: /编排门户/ }));
  fireEvent.change(screen.getByRole('textbox', { name: '门户标题' }), { target: { value: '新的服务台' } });
  fireEvent.click(screen.getByRole('button', { name: /取消编辑/ }));
  expect(api.savePortalLayout).not.toHaveBeenCalled();
  expect(screen.getByText('团队服务台')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /编排门户/ }));
  fireEvent.change(screen.getByRole('textbox', { name: '门户标题' }), { target: { value: '新的服务台' } });
  fireEvent.click(screen.getByRole('button', { name: /发布布局/ }));
  await waitFor(() => expect(api.savePortalLayout).toHaveBeenCalledWith(expect.objectContaining({ title: '新的服务台' })));
});
it('加载失败显示重试，不保存空配置', async () => {
  api.portalLayout.mockRejectedValueOnce(new Error('配置读取失败'));
  render(<App><PortalPage /></App>);
  await screen.findByText('配置读取失败');
  fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }));
  await screen.findByText('团队服务台');
  expect(api.savePortalLayout).not.toHaveBeenCalled();
});
it('组件可移除、重新添加和排序后发布', async () => {
  api.savePortalLayout.mockImplementation(async value => value);
  render(<App><PortalPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: /编排门户/ }));
  fireEvent.click(screen.getByRole('button', { name: '移除服务目录' }));
  expect(screen.queryByRole('heading', { name: /服务目录/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /plus\s*服务目录/ }));
  fireEvent.click(screen.getByRole('button', { name: /plus\s*我的待办/ }));
  fireEvent.click(screen.getByRole('button', { name: '上移我的待办' }));
  fireEvent.click(screen.getByRole('button', { name: /发布布局/ }));
  await waitFor(() => expect(api.savePortalLayout).toHaveBeenCalledWith(expect.objectContaining({ widgets: [{ type: 'todo', width: 6 }, { type: 'services', width: 6 }] })));
});
it('没有申请权限不展示申请链接，仍可搜索服务', async () => {
  const value = await api.portal();
  api.portal.mockResolvedValue({ ...value, can_apply: false });
  render(<App><PortalPage /></App>);
  await screen.findByText('电脑申请');
  expect(screen.queryByRole('link', { name: /电脑申请/ })).toBeNull();
});
it('不支持的背景图片不会保存', async () => {
  render(<App><PortalPage /></App>);
  fireEvent.click(await screen.findByRole('button', { name: /编排门户/ }));
  fireEvent.change(screen.getByLabelText('上传背景图'), { target: { files: [new File(['svg'], 'image.svg', { type: 'image/svg+xml' })] } });
  await screen.findByText('请选择 1 MB 以内的 PNG、JPEG 或 WebP 图片');
  expect(api.savePortalLayout).not.toHaveBeenCalled();
});
it('工作台展示真实工单、公告与趋势，移除目录后仍能搜索服务', async () => {
  api.portalLayout.mockResolvedValue({ title: '团队服务台', subtitle: '', background: '', widgets: ['stats', 'todo', 'tickets', 'trend', 'announcements', 'quick', 'recents', 'favorites'].map(type => ({ type, width: 6 })) });
  api.portalDashboard.mockResolvedValue({ stats: { total: 12, todo: 1, active: 3, finished: 9 }, can_view_tickets: true, todo: [{ id: 3, title: '我的审批', sn: 'REQ3', status: '处理中' }], tickets: [{ id: 4, title: '完成的申请', sn: 'REQ4', status: '已完成' }], trend: [{ date: '2026-11-13', created: 2, finished: 1 }], announcements: [{ id: 1, title: '维护公告', content: '请提前保存工作', created_at: '2026-11-13' }] });
  render(<App><PortalPage /></App>);
  expect((await screen.findByRole('link', { name: /我的审批/ })).getAttribute('href')).toBe('/itsm/tickets/3');
  expect(screen.getByRole('link', { name: /完成的申请/ }).getAttribute('href')).toBe('/itsm/tickets/4');
  expect(screen.getByRole('img', { name: '近十四天新建与完成工单趋势' })).toBeTruthy();
  fireEvent.click(screen.getByText('维护公告'));
  expect(screen.getByText('请提前保存工作')).toBeTruthy();
  fireEvent.change(screen.getByRole('textbox', { name: '搜索服务' }), { target: { value: '电脑' } });
  expect(screen.getByRole('link', { name: /电脑申请/ })).toBeTruthy();
  expect(screen.queryByRole('link', { name: /我的审批/ })).toBeNull();
});
