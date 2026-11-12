import { describe, expect, it } from 'vitest';

import { rumRouteLabel } from '@/app/rum/views/lib/route-label';

const translate = (key: string, fallback?: string) => (key === 'rum.views.otherRoute' ? '其他（超出路由上限）' : fallback || key);

describe('rumRouteLabel', () => {
  it('names the overflow route and leaves real routes unchanged', () => {
    expect(rumRouteLabel('其他', translate)).toBe('其他（超出路由上限）');
    expect(rumRouteLabel('/cart', translate)).toBe('/cart');
    expect(rumRouteLabel('unknown', translate)).toBe('unknown');
    expect(rumRouteLabel('', translate)).toBe('—');
  });
});
