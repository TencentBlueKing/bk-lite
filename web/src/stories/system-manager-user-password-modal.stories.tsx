import type { Meta, StoryObj } from '@storybook/nextjs';
import { useEffect, useRef } from 'react';
import { expect, userEvent, within } from 'storybook/test';
import PasswordModal, { PasswordModalRef } from '@/app/system-manager/components/user/passwordModal';

const PasswordModalStory = () => {
  const ref = useRef<PasswordModalRef>(null);

  useEffect(() => {
    ref.current?.showModal({ userId: 'demo-user' });
  }, []);

  return <PasswordModal ref={ref} onSuccess={() => {}} />;
};

const meta = {
  title: 'System Manager/User Org/PasswordModal',
  component: PasswordModalStory,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof PasswordModalStory>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  play: async () => {
    const modal = within(document.body);

    await expect(await modal.findByText('system.user.passwordTitle')).toBeInTheDocument();
    await expect(
      await modal.findByText('system.security.passwordLengthRange: 10-20')
    ).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireUppercase')).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireLowercase')).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireDigit')).toBeInTheDocument();
  },
};

export const ValidationHint: Story = {
  play: async () => {
    const modal = within(document.body);

    await expect(await modal.findByText('system.user.passwordTitle')).toBeInTheDocument();

    const passwordInput = document.body.querySelector('input[type="password"]') as HTMLInputElement | null;
    expect(passwordInput).not.toBeNull();

    await userEvent.type(passwordInput!, 'Abc1234567');

    await expect(await modal.findByText('system.user.passwordValidation')).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireUppercase')).toBeInTheDocument();
  },
};
