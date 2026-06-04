import type { Meta, StoryObj } from '@storybook/nextjs';
import { useEffect, useRef } from 'react';
import { expect, userEvent, within } from 'storybook/test';
import PasswordModal, { PasswordModalRef } from '@/app/system-manager/components/user/passwordModal';
import { passwordSettings } from './system-manager-user-org-modal.fixtures';

const PasswordModalStory = () => {
  const ref = useRef<PasswordModalRef>(null);

  useEffect(() => {
    ref.current?.showModal({ userId: 'demo-user' });
  }, []);

  return (
    <PasswordModal
      ref={ref}
      onSuccess={() => {}}
      fetchSystemSettings={async () => passwordSettings}
      setUserPasswordAction={async () => ({ success: true })}
    />
  );
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
    await expect(
      await modal.findByText(
        'system.security.passwordComplexity: system.security.requireUppercase、system.security.requireLowercase、system.security.requireDigit'
      )
    ).toBeInTheDocument();
  },
};

export const ValidationHint: Story = {
  play: async () => {
    const modal = within(document.body);
    const dialog = await modal.findByRole('dialog');

    await expect(await modal.findByText('system.user.passwordTitle')).toBeInTheDocument();

    const passwordInput = await within(dialog).findByLabelText('system.user.form.password', {
      selector: 'input',
    });

    await userEvent.type(passwordInput, 'Abc1234567');

    await expect(await modal.findByText('system.user.passwordValidation')).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireUppercase')).toBeInTheDocument();
  },
};
