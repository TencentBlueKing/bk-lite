import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import K8sGuide from '../k8sGuide';
import type { K8sMeta, K8sRenderParams, SourceItem } from '../../types/integration';

const api = vi.hoisted(() => ({
  getK8sCloudRegions: vi.fn(),
  getK8sReceiverEndpoint: vi.fn(),
}));

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/hooks/useCopy', () => ({ useCopy: () => ({ copy: vi.fn() }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));

afterEach(cleanup);
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
  });
});
beforeEach(() => {
  api.getK8sCloudRegions.mockReset().mockResolvedValue([{ id: 9, name: 'edge' }]);
  api.getK8sReceiverEndpoint.mockReset();
});

const source = { id: 1, name: 'Kubernetes', source_id: 'k8s' } as SourceItem;
const meta = {
  source_id: 'k8s',
  name: 'Kubernetes',
  description: '',
  receiver_url: '/api/v1/alerts/api/receiver_data/',
  method: 'POST',
  headers: {},
  push_source_id_default: 'k8s',
  push_source_id_configurable: true,
  image_reference: 'example/exporter:latest',
  download_files: [{ key: 'deploy_yaml', file_name: 'deploy.yaml', display_name: 'Download deployment YAML' }],
  notes: [],
} as K8sMeta;

const receiverUrl = 'https://9.9.9.9:443/api/v1/alerts/api/receiver_data/';

const renderGuide = (onDownload = vi.fn()) => render(
  <K8sGuide
    source={source}
    meta={meta}
    selectedTeamId="1"
    selectedTeamSecret="team-secret"
    onDownload={onDownload}
  />,
);

const downloadButton = () => screen.getByRole('button', { name: /Download deployment YAML/ });
const expectDownloadDisabled = (disabled: boolean) => {
  expect(downloadButton().hasAttribute('disabled')).toBe(disabled);
};

it('选择云区域后展示只读上报地址，下载只提交区域和监控源', async () => {
  const onDownload = vi.fn(async (_fileKey: string, _fileName: string, _params: K8sRenderParams) => undefined);
  api.getK8sReceiverEndpoint.mockResolvedValue({ receiver_url: receiverUrl });
  renderGuide(onDownload);

  await waitFor(() => expect(api.getK8sCloudRegions).toHaveBeenCalled());
  expect(screen.queryByPlaceholderText('https://10.11.27.147:443')).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'integration.serverUrlLabel' })).toBeNull();
  expectDownloadDisabled(true);

  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'integration.cloudRegionLabel' }));
  fireEvent.click(await screen.findByText('edge', { selector: '.ant-select-item-option-content' }));

  expect(await screen.findAllByText(receiverUrl)).not.toHaveLength(0);
  await waitFor(() => expectDownloadDisabled(false));
  fireEvent.click(downloadButton());

  expect(api.getK8sReceiverEndpoint).toHaveBeenCalledWith(9);
  expect(onDownload).toHaveBeenCalledWith('deploy_yaml', 'deploy.yaml', expect.objectContaining({
    cloud_region_id: 9,
    cluster_name: 'k8s_cluster',
    push_source_id: 'k8s',
    team_id: '1',
    insecure_skip_verify: true,
  }));
  expect(onDownload.mock.calls[0][2]).not.toHaveProperty('server_url');
});

it('上报地址解析失败时保持下载不可用', async () => {
  api.getK8sReceiverEndpoint.mockRejectedValue(new Error('当前云区域未配置 NODE_SERVER_URL，无法生成上报地址'));
  renderGuide();

  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'integration.cloudRegionLabel' }));
  fireEvent.click(await screen.findByText('edge', { selector: '.ant-select-item-option-content' }));

  expect((await screen.findByRole('alert')).textContent).toContain('NODE_SERVER_URL');
  expectDownloadDisabled(true);
});

it('没有云区域时提示先部署代理，且不能下载', async () => {
  api.getK8sCloudRegions.mockResolvedValue([]);
  renderGuide();

  expect(await screen.findByText('integration.cloudRegionEmpty')).toBeTruthy();
  expectDownloadDisabled(true);
});
