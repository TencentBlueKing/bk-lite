import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';

const searchValue = (params: URLSearchParams, keys: string[]) => {
  for (const key of keys) {
    const value = params.get(key);
    if (value) return value;
  }
  return '';
};

export const isMonitorViewDetailPath = (pathname: string): boolean =>
  (pathname || '').includes('/monitor/view/detail');

const identity = () => {
  const params = new URLSearchParams(window.location.search);
  return {
    objectName: searchValue(params, ['monitorObjDisplayName', 'name']),
    instanceName: searchValue(params, ['instance_name', 'instance_id']),
    monitorObjId: params.get('monitorObjId') || '',
  };
};

export function getMessage(): PageContextMessage {
  const { objectName, instanceName } = identity();
  return {
    title: `monitor-view-detail:${objectName || 'object'}:${instanceName || 'instance'}`,
    currentTime: [objectName, instanceName].filter(Boolean).join('::'),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  const { objectName, instanceName, monitorObjId } = identity();
  return {
    url: window.location.href,
    app: 'monitor',
    title: document.title || '指标详情',
    sections: [{
      id: 'view-detail-identity',
      label: '当前指标详情',
      content: [
        '正在查看旧指标详情',
        objectName ? `对象: ${objectName}` : '',
        monitorObjId ? `monitorObjId: ${monitorObjId}` : '',
        instanceName ? `实例: ${instanceName}` : '',
      ].filter(Boolean).join('\n'),
      priority: 10,
    }],
    images: [],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
