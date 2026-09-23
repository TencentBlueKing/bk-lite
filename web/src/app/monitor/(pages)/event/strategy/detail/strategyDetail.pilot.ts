import type { AiPageContext, PageContextMessage } from '@/components/ai-page-context/types';
import type { UserItem, ThresholdField } from '@/app/monitor/types';
import type { ChannelItem, SourceFeild } from '@/app/monitor/types/event';

export interface StrategyDetailSnapshotInput {
  name?: string;
  objectName?: string;
  source?: SourceFeild;
  schedule?: string | number | null;
  scheduleUnit?: string;
  period?: number | null;
  periodUnit?: string;
  expression?: string;
  thresholds?: ThresholdField[];
  noticeChannelTypes?: unknown[];
  noticeUsers?: unknown[];
  handlers?: unknown[];
  userList?: UserItem[];
  channels?: ChannelItem[];
}

const displayNameOnly = (identifier: unknown, userList: UserItem[]): string => {
  if (identifier == null || identifier === '') return '';
  const key = String(identifier);
  const user = userList.find(
    (item) => String(item.id) === key || item.username === key,
  );
  return (user?.display_name || '').trim();
};

const namesOf = (ids: unknown[] | undefined, userList: UserItem[]): string[] =>
  (ids || []).map((id) => displayNameOnly(id, userList)).filter(Boolean);

export const buildStrategyDetailContext = (
  input: StrategyDetailSnapshotInput,
): Partial<AiPageContext> => {
  const noticeNames = namesOf(input.noticeUsers, input.userList || []);
  const handlerNames = namesOf(input.handlers, input.userList || []);
  const thresholds = (input.thresholds || [])
    .filter((item) => item && (item.level || item.value != null))
    .map((item) => [item.level, item.method, item.value].filter((part) => part != null && part !== '').join(' '))
    .filter(Boolean);
  const channels = (input.noticeChannelTypes || [])
    .map((id) => {
      const channel = (input.channels || []).find((item) => String(item.id) === String(id));
      return channel?.name || channel?.channel_type || String(id);
    })
    .filter(Boolean);
  const detail = [
    '正在查看告警策略详情',
    input.name ? `名称: ${input.name}` : '',
    input.objectName ? `对象: ${input.objectName}` : '',
    input.source?.values?.length != null ? `监控目标: ${input.source.values.length}` : '',
    input.schedule != null ? `调度: ${input.schedule}${input.scheduleUnit || ''}` : '',
    input.period != null ? `持续时长: ${input.period}${input.periodUnit || ''}` : '',
    input.expression ? `表达式: ${input.expression}` : '',
    thresholds.length ? `阈值: ${thresholds.join('；')}` : '',
    channels.length ? `通知渠道: ${channels.join('、')}` : '',
  ].filter(Boolean);
  const people = [
    noticeNames.length ? `通知人: ${noticeNames.join('、')}` : '',
    handlerNames.length ? `处理人: ${handlerNames.join('、')}` : '',
  ].filter(Boolean);
  return {
    url: typeof window === 'undefined' ? '' : window.location.href,
    app: 'monitor',
    title: typeof document === 'undefined' ? '策略详情' : document.title || '策略详情',
    sections: [
      {
        id: 'strategy-detail',
        label: '策略详情',
        content: detail.join('\n'),
        priority: 9,
      },
      ...(people.length
        ? [{
          id: 'notice-people',
          label: '通知人与处理人',
          content: people.join('\n'),
          priority: 6,
        }]
        : []),
    ],
    images: [],
  };
};

let published: Partial<AiPageContext> | null = null;

export const publishStrategyDetailSnapshot = (next: Partial<AiPageContext> | null) => {
  published = next;
};

export function getMessage(): PageContextMessage {
  const name = published?.sections?.find((section) => section.id === 'strategy-detail')?.content || '';
  return {
    title: 'monitor-strategy-detail',
    currentTime: name.slice(0, 160),
  };
}

export function getTextContext(): Partial<AiPageContext> {
  return published || {
    app: 'monitor',
    title: typeof document === 'undefined' ? '策略详情' : document.title,
    sections: [{
      id: 'strategy-detail',
      label: '策略详情',
      content: '正在查看告警策略详情',
      priority: 9,
    }],
    images: [],
  };
}

export async function getContext(): Promise<Partial<AiPageContext>> {
  return getTextContext();
}
