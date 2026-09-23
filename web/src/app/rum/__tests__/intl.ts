import { flattenMessages } from '@/app/apm/__tests__/intl';
import commonZh from '@/locales/zh.json';
import rumZh from '@/app/rum/locales/zh.json';

interface NestedMessages { [key: string]: string | NestedMessages }

export const rumZhMessages = {
  ...flattenMessages(commonZh as NestedMessages),
  ...flattenMessages(rumZh as NestedMessages),
};
