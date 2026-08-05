import React from 'react';
import { Meta, StoryFn } from '@storybook/nextjs';
import PageLayout from '@/components/page-layout';

export default {
  title: 'Components/PageLayout',
  component: PageLayout,
} as Meta<typeof PageLayout>;

const Template: StoryFn<typeof PageLayout> = (args) => <PageLayout {...args} />;

export const Default = Template.bind({});
Default.args = {
  rightSection: <div style={{ color: 'white' }}>Right Section Content</div>,
};

export const WithTopSection = Template.bind({});
WithTopSection.args = {
  topSection: <div style={{ color: 'white' }}>Top Section Content</div>,
  rightSection: <div style={{ color: 'white' }}>Right Section Content</div>,
};

export const WithLeftSection = Template.bind({});
WithLeftSection.args = {
  leftSection: <div style={{ color: 'white' }}>Left Section Content</div>,
  rightSection: <div style={{ color: 'white' }}>Right Section Content</div>,
};

export const FullLayout = Template.bind({});
FullLayout.args = {
  topSection: <div style={{ color: 'white' }}>Top Section Content</div>,
  leftSection: <div style={{ color: 'white' }}>Left Section Content</div>,
  rightSection: <div style={{ color: 'white' }}>Right Section Content</div>,
};
