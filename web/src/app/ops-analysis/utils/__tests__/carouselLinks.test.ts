import { describe, expect, it } from 'vitest';
import {
  carouselGuardIsCurrent,
  carouselViewDecision,
  resolveRequestedCarouselView,
} from '@/app/ops-analysis/utils/carouselLinks';

const carousel = { panel: 'carousel' as const, carouselId: '3' };
const directory = { panel: 'directory' as const, carouselId: null };

describe('carousel view guard', () => {
  it('reads the panel and carousel id from the address', () => {
    expect(resolveRequestedCarouselView('panel=carousel&carousel=3')).toEqual(carousel);
    expect(resolveRequestedCarouselView('panel=carousel&carousel=new')).toEqual({
      panel: 'carousel',
      carouselId: null,
    });
    expect(resolveRequestedCarouselView('')).toEqual(directory);
  });

  it('keeps the confirmed panel until a dirty leave is accepted', () => {
    expect(carouselViewDecision(carousel, carousel, true)).toBe('stay');
    expect(carouselViewDecision(carousel, directory, false)).toBe('apply');
    expect(carouselViewDecision(carousel, directory, true)).toBe('confirm');
    expect(carouselViewDecision(carousel, { panel: 'carousel', carouselId: '4' }, true)).toBe('confirm');
  });

  it('ignores an older back or forward confirmation', () => {
    expect(carouselGuardIsCurrent(2, 2)).toBe(true);
    expect(carouselGuardIsCurrent(3, 2)).toBe(false);
  });
});
