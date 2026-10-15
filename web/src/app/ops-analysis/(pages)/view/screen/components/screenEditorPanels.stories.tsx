import { useState } from 'react';
import { IntlProvider } from 'react-intl';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { ScreenElementPalette } from './screenEditorPanels';
import {
  createScreenClockItem,
  createScreenDecorationItem,
  createScreenTextItem,
  createScreenTitleFrameItem,
} from '../utils/screenItems';
import zhOps from '@/app/ops-analysis/locales/zh.json';
import zhCommon from '@/locales/zh.json';

type LocaleJson = Record<string, unknown>;
const flatten = (obj: LocaleJson, prefix = '', out: Record<string, string> = {}) => {
  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const next = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as LocaleJson, next, out);
    } else {
      out[next] = String(value);
    }
  });
  return out;
};

const messages = {
  ...flatten(zhCommon as LocaleJson),
  ...flatten(zhOps as LocaleJson),
};

const sampleItems = [
  createScreenTitleFrameItem([], {
    id: 'title-1',
    preset: 'hero-1',
    content: '运营大屏',
    zIndex: 4,
  }),
  createScreenClockItem([], { id: 'clock-1', zIndex: 3 }),
  createScreenTextItem([], { id: 'text-1', content: '说明', zIndex: 2 }),
  createScreenDecorationItem([], 'panelFrame', 'a', {
    id: 'frame-1',
    zIndex: 1,
  }),
];

const meta: Meta = {
  title: 'ops-analysis/ScreenElementPalette',
};

export default meta;

export const LockedPaletteAndList: StoryObj = {
  render: () => {
    const PaletteDemo = () => {
      const [selectedItemId, setSelectedItemId] = useState<string | null>('title-1');
      const [items, setItems] = useState(sampleItems);
      return (
        <IntlProvider locale="zh" messages={messages}>
          <div
            className="relative h-[720px] w-[640px] overflow-hidden border border-(--color-border-1)"
            data-screen-editor
          >
            <ScreenElementPalette
              selectedItemId={selectedItemId}
              items={items}
              onSelectItem={setSelectedItemId}
              onAddText={() => undefined}
              onAddClock={() => undefined}
              onAddTitleFrame={() => undefined}
              onAddDecoration={() => undefined}
              onAddShape={() => undefined}
              onOpenChartSelector={() => undefined}
              onOpenItemMenu={() => undefined}
              onReorderItem={() => undefined}
            />
          </div>
        </IntlProvider>
      );
    };
    return <PaletteDemo />;
  },
};
