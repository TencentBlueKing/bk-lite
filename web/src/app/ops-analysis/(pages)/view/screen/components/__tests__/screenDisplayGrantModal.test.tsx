import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Modal } from 'antd';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ScreenDisplayGrantModal from '../screenDisplayGrantModal';

const getGrant = vi.hoisted(() => vi.fn());
const pauseGrant = vi.hoisted(() => vi.fn());

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/api/screenDisplay', () => ({
  SCREEN_DISPLAY_DURATIONS: [1, 7, 30, 90],
  useScreenDisplayApi: () => ({
    getGrant,
    createGrant: vi.fn(),
    pauseGrant,
    resumeGrant: vi.fn(),
    regenerateGrant: vi.fn(),
  }),
}));

describe('screen display grant modal', () => {
  afterEach(() => {
    Modal.destroyAll();
    cleanup();
  });

  it('offers one link with copy, pause, and regenerate, and no login action', async () => {
    getGrant.mockResolvedValue({
      configured: true,
      state: 'active',
      duration_days: 30,
      expires_at: '2026-12-12T00:00:00Z',
      url: '/ops-analysis/display/t/signed-token',
    });

    render(
      <ScreenDisplayGrantModal open screenId={7} onClose={() => undefined} />,
    );

    expect(await screen.findByRole('button', { name: 'opsAnalysis.screen.displayCopy' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.displayPause' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.displayRegenerate' })).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.displayDurationHint')).toBeTruthy();
    expect(screen.getByText(/opsAnalysis\.screen\.displayExpiresAt/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /登录|sign in/i })).toBeNull();
    await waitFor(() => {
      expect(screen.getByText(/\/ops-analysis\/display\/t\/signed-token/)).toBeTruthy();
    });
  });

  it('asks before pausing and does not disable the link until confirmed', async () => {
    getGrant.mockResolvedValue({
      configured: true,
      state: 'active',
      duration_days: 30,
      expires_at: '2026-12-12T00:00:00Z',
      url: '/ops-analysis/display/t/signed-token',
    });
    pauseGrant.mockReset();

    render(
      <ScreenDisplayGrantModal open screenId={7} onClose={() => undefined} />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'opsAnalysis.screen.displayPause' }));
    expect(await screen.findAllByText('opsAnalysis.screen.displayPauseConfirmTitle')).not.toHaveLength(0);
    expect(screen.getAllByText('opsAnalysis.screen.displayPauseConfirm').length).toBeGreaterThan(0);
    expect(pauseGrant).not.toHaveBeenCalled();
  });

  it('hides the access link while the grant is paused', async () => {
    getGrant.mockResolvedValue({
      configured: true,
      state: 'paused',
      duration_days: 30,
      expires_at: '2026-12-12T00:00:00Z',
      url: '/ops-analysis/display/t/signed-token',
    });

    render(
      <ScreenDisplayGrantModal open screenId={7} onClose={() => undefined} />,
    );

    expect(await screen.findByText('opsAnalysis.screen.displayStatusBadge.paused')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.displayRegenerate' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'opsAnalysis.screen.displayResume' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'opsAnalysis.screen.displayCopy' })).toBeNull();
    expect(screen.queryByText(/signed-token/)).toBeNull();
  });

  it('shows an empty result before a link exists', async () => {
    getGrant.mockResolvedValue({
      configured: false,
      state: 'absent',
      duration_days: 30,
      expires_at: null,
      url: '',
    });

    render(
      <ScreenDisplayGrantModal open screenId={7} onClose={() => undefined} />,
    );

    expect(await screen.findByRole('button', { name: 'opsAnalysis.screen.displayCreate' })).toBeTruthy();
    expect(screen.getByText('opsAnalysis.screen.displayEmpty')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'opsAnalysis.screen.displayCopy' })).toBeNull();
    expect(screen.queryByText(/opsAnalysis\.screen\.displayExpiresAt/)).toBeNull();
    expect(screen.queryByText('opsAnalysis.screen.displayStatusBadge.active')).toBeNull();
  });
});
