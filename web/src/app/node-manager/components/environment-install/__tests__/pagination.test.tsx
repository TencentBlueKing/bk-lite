import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/utils/request', () => ({ default: () => api }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => ({ selectedGroup: { id: 1, name: 'Test' } }) }));
import EnvironmentInstall from '../index';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: () => ({
    matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}
  }) });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('requests grants for the active cloud region and fetches the next server page', async () => {
  api.get.mockImplementation(async (url: string, config?: { params?: { page?: number } }) => {
    if (url.endsWith('/grants/')) return { count: 11, items: [{
      id: `grant-${config?.params?.page || 1}`, cloud_region_id: 7,
      package_version: `page-${config?.params?.page || 1}`, used_nodes: 0,
      max_nodes: 2, enabled: true, expires_at: '2030-01-01T00:00:00Z'
    }] };
    if (url.endsWith('/package/')) return { count: 0, items: [] };
    return [];
  });
  render(<EnvironmentInstall open cloudId={7} onClose={() => undefined} />);
  await waitFor(() => expect(api.get).toHaveBeenCalledWith(
    '/node_mgmt/api/environment_install/grants/', { params: { cloud_region_id: 7, page: 1, page_size: 10 } }
  ));
  fireEvent.click(screen.getByRole('tab', { name: 'node-manager.environmentBundle.grantsTab' }));
  await screen.findByText('page-1');
  fireEvent.click(screen.getByTitle('2'));
  await screen.findByText('page-2');
  expect(api.get).toHaveBeenCalledWith('/node_mgmt/api/environment_install/grants/', {
    params: { cloud_region_id: 7, page: 2, page_size: 10 }
  });
  expect(screen.queryByText('page-1')).toBeNull();
});

it('fetches result pages from the server for the selected grant', async () => {
  api.get.mockImplementation(async (url: string) => url.endsWith('/grants/') ? {
    count: 1, items: [{ id: 'grant-a', cloud_region_id: 7, package_version: 'v1', used_nodes: 1001, max_nodes: 2000, enabled: true, expires_at: '2030-01-01' }]
  } : url.endsWith('/package/') ? { count: 0, items: [] } : []);
  api.post.mockImplementation(async (_url: string, data: { page?: number }) => ({ count: 1001, items: [{
    id: `result-${data.page}`, node_id: `node-${data.page}`, node_name: `host-page-${data.page}`, ip: '192.0.2.1', registered_at: null, failure_stage: '', error_code: 0
  }] }));
  render(<EnvironmentInstall open cloudId={7} onClose={() => undefined} />);
  fireEvent.click(screen.getByRole('tab', { name: 'node-manager.environmentBundle.grantsTab' }));
  fireEvent.click(await screen.findByRole('button', { name: 'node-manager.environmentBundle.results' }));
  await screen.findByText('host-page-1');
  fireEvent.click(screen.getByTitle('101'));
  await screen.findByText('host-page-101');
  expect(api.post).toHaveBeenLastCalledWith('/node_mgmt/api/environment_install/results/', { grant_id: 'grant-a', page: 101, page_size: 10 });
  expect(screen.queryByText('host-page-1')).toBeNull();
});
