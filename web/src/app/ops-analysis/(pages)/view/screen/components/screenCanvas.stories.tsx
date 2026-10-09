import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import ScreenCanvas from './screenCanvas';
import {
  createScreenClockItem,
  createScreenDecorationItem,
  createScreenTitleFrameItem,
} from '../utils/screenItems';

const items = [
  createScreenTitleFrameItem([], {
    id: 'title-1',
    preset: 'hero-1',
    content: '运营大屏',
    x: 585,
    y: 24,
    zIndex: 3,
  }),
  createScreenClockItem([], {
    id: 'clock-1',
    x: 1480,
    y: 28,
    zIndex: 2,
  }),
  createScreenDecorationItem([], 'panelFrame', 'a', {
    id: 'frame-1',
    x: 48,
    y: 280,
    zIndex: 1,
  }),
];

const meta: Meta = {
  title: 'ops-analysis/ScreenCanvasChrome',
};

export default meta;

export const EditSelectChrome: StoryObj = {
  render: () => {
    const Demo = () => {
      const [selectedItemId, setSelectedItemId] = useState<string | null>('title-1');
      return (
        <div className="h-[640px] w-[1100px]">
          <ScreenCanvas
            viewSets={{
              viewport: {
                width: 1920,
                height: 1080,
                theme: 'screen-dark',
                adapter: 'fill',
                background: { type: 'preset', key: 'dark-glow' },
              },
              items,
              decorations: {},
            }}
            editMode
            selectedItemId={selectedItemId}
            onSelectItem={setSelectedItemId}
          />
        </div>
      );
    };
    return <Demo />;
  },
};
