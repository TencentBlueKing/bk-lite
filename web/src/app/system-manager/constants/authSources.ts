import { AuthSourceTypeConfig } from '@/app/system-manager/types/security';

export const AUTH_SOURCE_TYPE_MAP: Record<string, AuthSourceTypeConfig> = {
  wechat: {
    icon: 'weixingongzhonghao',
    description: '支持微信平台扫码登录'
  },
  'bk_lite': {
    icon: 'dengdeng',
    description: '支持BK-Lite认证源'
  },
  'blueking': {
    icon: 'blueking-icon',
    description: '支持蓝鲸平台认证源'
  },
};