import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ServiceTagOverflow, {
  computeVisibleServiceTagCount,
} from '../service-tag-overflow';
import { renderWithApmIntl } from '@/app/apm/__tests__/intl';

const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
const originalClientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');

afterEach(() => {
  cleanup();
  Element.prototype.getBoundingClientRect = originalGetBoundingClientRect;
  if (originalClientWidth) {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', originalClientWidth);
  }
});

describe('computeVisibleServiceTagCount', () => {
  it('全部放得下时不折叠', () => {
    expect(computeVisibleServiceTagCount([40, 40, 40], 140, 38)).toBe(3);
  });

  it('放不下时预留 +N 宽度并折叠', () => {
    // 40+6+40+6+38 = 130 > 120 → 只能放下 1 个 + badge
    expect(computeVisibleServiceTagCount([40, 40, 40], 120, 38)).toBe(1);
  });

  it('连第一个 tag 都放不下时可见数为 0，只靠 +N', () => {
    expect(computeVisibleServiceTagCount([200, 40], 80, 38)).toBe(0);
  });

  it('空列表或零宽度容器返回 0', () => {
    expect(computeVisibleServiceTagCount([], 200, 38)).toBe(0);
    expect(computeVisibleServiceTagCount([40], 0, 38)).toBe(0);
  });
});

describe('ServiceTagOverflow', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('无服务时展示空态文案且占用同一行高', () => {
    const { container } = renderWithApmIntl(<ServiceTagOverflow services={[]} />);
    expect(screen.getByText('尚无服务上报')).not.toBeNull();
    expect(container.querySelector('.h-6')).not.toBeNull();
  });

  it('溢出徽章可打开完整服务列表且不冒泡', async () => {
    const user = userEvent.setup();
    const onOuterClick = vi.fn();

    Element.prototype.getBoundingClientRect = vi.fn(function getBoundingClientRect(this: Element) {
      const isBadge = this.getAttribute('data-service-tag-overflow-badge-measure') === 'true';
      const width = isBadge ? 36 : 120;
      return {
        width,
        height: 20,
        top: 0,
        left: 0,
        bottom: 20,
        right: width,
        x: 0,
        y: 0,
        toJSON() {},
      } as DOMRect;
    });
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        return 80;
      },
    });

    renderWithApmIntl(
      <div onClick={onOuterClick}>
        <ServiceTagOverflow
          services={[
            { name: 'demo-catalog', silent: false },
            { name: 'demo-inventory', silent: true },
            { name: 'demo-orders', silent: false },
          ]}
        />
      </div>,
    );

    const overflow = await screen.findByRole('button', { name: /还有 .* 个服务未展示/ });
    await user.click(overflow);

    expect(onOuterClick).not.toHaveBeenCalled();
    const list = await screen.findByRole('list');
    expect(within(list).getByText('demo-catalog')).not.toBeNull();
    expect(within(list).getByText('demo-inventory')).not.toBeNull();
    expect(within(list).getByText('静默')).not.toBeNull();
    expect(screen.getByText('共 3 个')).not.toBeNull();
    expect(overflow.className).not.toMatch(/min-h-10/);
    expect(overflow.className).toMatch(/\bh-6\b/);
    expect(overflow.parentElement?.className).toContain('h-6');
    const track = overflow.closest('.relative');
    expect(track?.className).toContain('w-full');
    expect(track?.className).toContain('min-w-0');
    expect(track?.className).toContain('overflow-hidden');
  });
});
