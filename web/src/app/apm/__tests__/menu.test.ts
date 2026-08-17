import menu from '@/app/apm/constants/menu.json';

describe('APM 二级菜单图标', () => {
  it.each(['zh', 'en'] as const)('%s 服务拓扑使用图标库内的拓扑图标', (locale) => {
    const services = menu[locale].find((item) => item.url === '/apm/services');
    const topology = services?.children?.find((item) => item.url === '/apm/services/topology');

    expect(topology?.icon).toBe('tuoputu');
  });
});
