import type { Meta, StoryObj } from '@storybook/nextjs';
import WithSideMenuLayout from '@/components/sub-layout/index';
import { MenuItem } from '@/types/index';
import { Segmented } from 'antd';
import Icon from '@/components/icon';
import SideMenu from '@/components/sub-layout/side-menu';
import React from 'react';

const meta: Meta<typeof WithSideMenuLayout> = {
  title: 'Components/Layouts/WithSideMenuLayout',
  component: WithSideMenuLayout,
  args: {
    intro: <div>Introduction Content</div>,
    showBackButton: true,
    onBackButtonClick: () => alert('Back button clicked'),
    children: <div>Main Content</div>,
    topSection: <div>Top Section Content</div>,
    showProgress: true,
    layoutType: 'sideMenu',
  },
};

export default meta;

type Story = StoryObj<typeof WithSideMenuLayout>;

// Define menu items to be used across stories
const sampleMenuItems: MenuItem[] = [
  { title: 'Home', url: '/', icon: 'home', name: 'home', operation: ['View'] },
  { title: 'Dashboard', url: '/dashboard', icon: 'dashboard', name: 'dashboard', operation: ['View'] },
];

// Default layout with SideMenu
export const Default: Story = {
  args: {
    showSideMenu: true,
    taskProgressComponent: <div>Task Progress Placeholder</div>,
  },
  render: (args) => (
    <WithSideMenuLayout {...args}>
      <SideMenu
        menuItems={sampleMenuItems}
        showBackButton={args.showBackButton}
        showProgress={args.showProgress}
        taskProgressComponent={args.taskProgressComponent}
        onBackButtonClick={args.onBackButtonClick}
      >
        {args.intro}
      </SideMenu>
      {args.children}
    </WithSideMenuLayout>
  ),
};

// Example without SideMenu
export const WithoutSideMenu: Story = {
  args: {
    showSideMenu: false,
    layoutType: 'segmented',
  },
  render: (args) => (
    <WithSideMenuLayout {...args}>
      <Segmented
        options={sampleMenuItems.map(item => ({
          label: (
            <div className="flex items-center justify-center">
              {item.icon && (
                <Icon type={item.icon} className="mr-2 text-sm" />
              )} {item.title}
            </div>
          ),
          value: item.url,
        }))}
        value={''}
        onChange={(() => {})}
      />
      {args.children}
    </WithSideMenuLayout>
  ),
};

// Example of the Segmented Layout
export const SegmentedLayout: Story = {
  args: {
    showSideMenu: false,
    layoutType: 'segmented',
  },
  render: (args) => (
    <WithSideMenuLayout {...args}>
      <Segmented
        options={sampleMenuItems.map(item => ({
          label: (
            <div className="flex items-center justify-center">
              {item.icon && (
                <Icon type={item.icon} className="mr-2 text-sm" />
              )} {item.title}
            </div>
          ),
          value: item.url,
        }))}
        value={''}
        onChange={(() => {})}
      />
      {args.children}
    </WithSideMenuLayout>
  ),
};
