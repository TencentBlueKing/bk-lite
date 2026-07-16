import type {
  FunctionMenuItem,
  SourceMenuNode,
} from '@/components/system-manager-application-menu/types';

export const systemManagerSourceMenus: SourceMenuNode[] = [
  {
    name: 'monitor',
    display_name: 'Monitor',
    url: '/monitor',
    icon: 'jiankong',
    type: 'menu',
    children: [
      {
        name: 'dashboard',
        display_name: 'Dashboard',
        url: '/monitor/dashboard',
        icon: 'dashboard',
        type: 'page',
      },
      {
        name: 'alert-policy',
        display_name: 'Alert Policy',
        url: '/monitor/alarm/policy',
        icon: 'gaojing',
        type: 'page',
      },
    ],
  },
  {
    name: 'cmdb-detail',
    display_name: 'Asset Detail',
    url: '/cmdb/asset/detail',
    icon: 'ziyuan',
    type: 'page',
    isDetailMode: true,
  },
];

export const systemManagerGroupPages: FunctionMenuItem[] = [
  {
    name: 'dashboard-overview',
    display_name: 'Dashboard Overview',
    originName: 'Overview',
    url: '/monitor/dashboard/overview',
    icon: 'dashboard',
    type: 'page',
  },
  {
    name: 'alert-policy',
    display_name: 'Alert Policy',
    url: '/monitor/alarm/policy',
    icon: 'gaojing',
    type: 'page',
  },
];

export const systemManagerMenuPage: FunctionMenuItem = {
  name: 'dashboard-overview',
  display_name: 'Dashboard Overview',
  originName: 'Overview',
  url: '/monitor/dashboard/overview',
  icon: 'dashboard',
  type: 'page',
};
