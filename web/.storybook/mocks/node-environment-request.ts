// Preview-only data. No endpoint reaches a real platform and no installer is generated.
export type EnvironmentPreviewState = 'ready' | 'empty' | 'error' | 'long';
let state: EnvironmentPreviewState = 'ready';
let enabled = true;
export const configureEnvironmentPreview = (next: EnvironmentPreviewState) => { state = next; enabled = true; };

export const environmentPreviewGet = (url: string): unknown => {
  if (!url.startsWith('/node_mgmt/api/')) return undefined;
  if (state === 'error') throw new Error('Preview service unavailable');
  if (url.includes('/environment_install/components/')) return state === 'empty' ? [] : [{ id: 'telegraf-linux', name: 'Telegraf' }];
  if (url.includes('/package/')) {
    const items = state === 'empty' ? [] : [{ id: 1, version: state === 'long' ? 'controller-2026.11.12-enterprise-linux-x86_64-internal-release' : '4.0.0-preview', sha256: 'a'.repeat(64) }];
    return { count: items.length, items };
  }
  if (url.includes('/environment_install/grants/')) return { count: state === 'empty' ? 0 : 1, items: state === 'empty' ? [] : [{ id: 'a924ac2f-9660-4131-9b37-205ea96e9d44', cloud_region_id: 1, package_version: '4.0.0-preview', used_nodes: 2, max_nodes: 100, enabled, expires_at: '2030-11-19T00:00:00Z' }] };
  return undefined;
};

export const environmentPreviewPost = (url: string): unknown => {
  if (!url.includes('/node_mgmt/api/environment_install/')) return undefined;
  if (url.endsWith('/export/')) throw new Error('Preview does not generate installation credentials');
  if (url.endsWith('/revoke/')) { enabled = false; return {}; }
  if (url.endsWith('/results/')) return { count: 2, items: [
    { id: '1', node_id: '8d3205cf-b44c-40c0-8cfe-08ff8a9d7104', node_name: 'preview-host-01', ip: '192.0.2.10', registered_at: '2026-11-12T13:15:00Z', failure_stage: '', error_code: 0 },
    { id: '2', node_id: '2e015eb6-9574-4e8b-b98c-087eb97f7679', node_name: 'preview-host-02', ip: '192.0.2.11', registered_at: null, failure_stage: 'download', error_code: 30 }
  ] };
  return {};
};
