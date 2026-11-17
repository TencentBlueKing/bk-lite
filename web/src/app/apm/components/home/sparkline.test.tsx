import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import Sparkline from '@/app/apm/components/home/sparkline';

describe('Sparkline', () => {
  it('keeps a continuous series as one line and breaks missing buckets', () => {
    const continuous = render(<Sparkline data={[1, 2, 3]} />);
    expect(continuous.container.querySelectorAll('path')).toHaveLength(1);
    expect(continuous.container.querySelectorAll('circle')).toHaveLength(0);

    const gapped = render(<Sparkline data={[1, null, 3]} />);
    expect(gapped.container.querySelectorAll('path')).toHaveLength(0);
    expect(gapped.container.querySelectorAll('circle')).toHaveLength(2);

    const broken = render(<Sparkline data={[1, 2, null, 4, 5]} />);
    expect(broken.container.querySelectorAll('path')).toHaveLength(2);

    const dot = render(<Sparkline data={[null, 5, null]} />);
    expect(dot.container.querySelectorAll('circle')).toHaveLength(1);
    expect(dot.container.querySelectorAll('path')).toHaveLength(0);
  });
});
