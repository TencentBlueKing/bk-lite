import { AuthSourceTypeConfig } from '@/app/system-manager/types/security';

export const getAuthSourceTypeMap = (t: (key: string) => string): Record<string, AuthSourceTypeConfig> => ({
  wechat: {
    icon: 'weixingongzhonghao',
    description: t('system.security.authSourceWechatDescription')
  },
  'bk_lite': {
    icon: 'dengdeng',
    description: t('system.security.authSourceBkLiteDescription')
  },
  bk_login: {
    icon: 'blueking-icon',
    description: t('system.security.authSourceBluekingDescription')
  },
  'blueking': {
    icon: 'blueking-icon',
    description: t('system.security.authSourceBluekingDescription')
  },
});
