import { captureEchartsFromDom } from '@/components/ai-page-context/chart-capture';
import type { AiPageContext } from '@/components/ai-page-context/types';

const searchValue = (params: URLSearchParams, keys: string[]) => {
  for (const key of keys) {
    const value = params.get(key);
    if (value) return value;
  }
  return '';
};

export async function collect(): Promise<Partial<AiPageContext>> {
  const params = new URLSearchParams(window.location.search);
  const segments = window.location.pathname.split('/').filter(Boolean);
  const objectKey = segments[segments.length - 1] || '';
  const objectName = searchValue(params, ['name', 'monitorObjDisplayName']) || objectKey;
  const instanceName = searchValue(params, ['instance_name', 'instance_id']);
  const view = params.get('view') || 'dashboard';
  const lines = [
    `正在查看监控专业仪表盘`,
    objectName ? `对象: ${objectName}` : '',
    objectKey ? `objectKey: ${objectKey}` : '',
    params.get('monitorObjId') ? `monitorObjId: ${params.get('monitorObjId')}` : '',
    instanceName ? `实例: ${instanceName}` : '',
    `视图: ${view}`,
  ].filter(Boolean);

  const images = await captureEchartsFromDom();
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || `${objectName} 仪表盘`,
    sections: [
      {
        id: 'dashboard-identity',
        label: '当前仪表盘',
        content: lines.join('\n'),
        priority: 10,
      },
    ],
    images,
  };
}
