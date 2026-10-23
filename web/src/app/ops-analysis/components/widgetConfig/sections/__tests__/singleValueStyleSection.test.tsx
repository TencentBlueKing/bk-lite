import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Form, message } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { FormInstance } from 'antd';
import type { SingleValueStyleConfig } from '@/app/ops-analysis/utils/singleValueStyle';
import {
  ScreenSingleValueStyleSections,
  SingleValueStyleSection,
} from '../singleValueStyleSection';

const showModal = vi.fn();

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/cmdb/utils/modelIcon', () => ({
  getModelIconUrl: ({ icn }: { icn: string }) => `/assets/${icn}.svg`,
}));

vi.mock('@/app/cmdb/(pages)/assetManage/management/list/selectIcon', () => {
  function MockSelectIcon(
    props: { onSelect: (iconKey: string) => void },
    ref: React.Ref<{ showModal: (info: unknown) => void }>,
  ) {
    React.useImperativeHandle(ref, () => ({
      showModal: (info: unknown) => {
        showModal(info);
      },
    }));
    return (
      <button type="button" data-testid="select-icon-confirm" onClick={() => props.onSelect('cc-host')}>
        pick
      </button>
    );
  }
  return { default: React.forwardRef(MockSelectIcon) };
});

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  showModal.mockClear();
});

const Harness: React.FC<{
  initial?: SingleValueStyleConfig;
  itemId?: string;
  onStyleChange?: (next: SingleValueStyleConfig | undefined) => void;
}> = ({ initial, itemId, onStyleChange }) => {
  const [style, setStyle] = useState<SingleValueStyleConfig | undefined>(initial);
  return (
    <ScreenSingleValueStyleSections
      itemId={itemId}
      t={(key) => key}
      style={style}
      onStyleChange={(next) => {
        setStyle(next);
        onStyleChange?.(next);
      }}
    />
  );
};

const sourceRadio = (name: string) => screen.getByRole('radio', { name }) as HTMLInputElement;

describe('SingleValueStyleSection on a real form', () => {
  const Harness = ({
    formRef,
    initial,
  }: {
    formRef: { current: FormInstance | null };
    initial?: SingleValueStyleConfig;
  }) => {
    const [form] = Form.useForm();
    formRef.current = form;
    return (
      <Form
        form={form}
        initialValues={{
          singleStyle: initial || {
            showIcon: false,
            iconPosition: 'left',
            iconSize: 'medium',
          },
        }}
      >
        <SingleValueStyleSection t={(key) => key} />
      </Form>
    );
  };

  it('updates the switch, alignment and registered form value together', async () => {
    const formRef: { current: FormInstance | null } = { current: null };
    render(<Harness formRef={formRef} />);

    expect(screen.queryByText('dashboard.singleStyleIconSource')).toBeNull();
    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));

    expect(await screen.findByText('dashboard.singleStyleIconSource')).toBeTruthy();
    expect(sourceRadio('dashboard.singleStyleIconBuiltin').checked).toBe(true);
    expect(sourceRadio('dashboard.singleStyleIconUpload').checked).toBe(false);
    expect(showModal).not.toHaveBeenCalled();
    expect(screen.queryByTestId('single-style-file-input')).toBeNull();
    expect(formRef.current?.getFieldsValue().singleStyle.showIcon).toBe(true);
    expect(formRef.current?.getFieldsValue().singleStyle.iconSource).toBe('builtin');

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }));
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignLeft' }).getAttribute('aria-pressed')).toBe('false');

    const saved = await formRef.current?.validateFields();
    expect(saved?.singleStyle.showIcon).toBe(true);
    expect(saved?.singleStyle.align).toBe('center');
    expect(saved?.singleStyle.iconSource).toBe('builtin');
  });

  it('drops another widget\'s unpersisted icon when the form is refilled', async () => {
    const formRef: { current: FormInstance | null } = { current: null };
    render(<Harness formRef={formRef} />);

    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));
    fireEvent.click(screen.getByTestId('single-style-icon-cell'));
    fireEvent.click(screen.getByTestId('select-icon-confirm'));
    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));
    expect(formRef.current?.getFieldsValue().singleStyle.iconKey).toBe('cc-host');

    act(() => {
      formRef.current?.setFieldsValue({
        singleStyle: {
          showIcon: true,
          iconSource: 'builtin',
          iconKey: undefined,
          iconImage: undefined,
          iconPosition: 'left',
          iconSize: 'medium',
          align: undefined,
        },
      });
    });

    await waitFor(() => {
      const refilled = formRef.current?.getFieldValue('singleStyle');
      expect(refilled.iconSource).toBe('builtin');
      expect(refilled.iconKey).toBeUndefined();
      expect(screen.getByText('dashboard.singleStyleIconBuiltin').closest('label')?.className)
        .toContain('ant-radio-button-wrapper-checked');
      expect(screen.getByTestId('single-style-icon-cell').querySelector('img')).toBeNull();
    });

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }));
    expect(formRef.current?.getFieldsValue().singleStyle.iconKey).toBeUndefined();
    expect(formRef.current?.getFieldsValue().singleStyle.align).toBe('center');
  });
});

describe('ScreenSingleValueStyleSections', () => {
  it('keeps the icon body empty until the switch is on, then selects builtin without opening the library', () => {
    render(<Harness />);

    expect(screen.queryByText('dashboard.singleStyleIconSource')).toBeNull();
    expect(screen.queryByText('dashboard.singleStyleIconPosition')).toBeNull();
    expect(screen.queryByText('dashboard.singleStyleIconHint')).toBeNull();
    expect(screen.queryByText('dashboard.singleStyleAlignHintScreen')).toBeNull();
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignLeft' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignRight' }).getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));

    expect(sourceRadio('dashboard.singleStyleIconBuiltin').checked).toBe(true);
    expect(sourceRadio('dashboard.singleStyleIconUpload').checked).toBe(false);
    expect(showModal).not.toHaveBeenCalled();
    expect(screen.queryByTestId('single-style-file-input')).toBeNull();
    expect(screen.getByTestId('single-style-icon-cell').getAttribute('aria-label')).toBe('dashboard.singleStyleSelectIcon');
    expect(screen.getByRole('button', { name: 'dashboard.singleStylePositionLeft' }).className).toContain('whitespace-nowrap');
    fireEvent.click(screen.getByTestId('single-style-icon-cell'));
    expect(showModal).toHaveBeenCalledTimes(1);
  });

  it('keeps the other source while editing and persists only the active one', async () => {
    const onStyleChange = vi.fn();
    render(<Harness itemId="card-a" onStyleChange={onStyleChange} />);

    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));
    fireEvent.click(sourceRadio('dashboard.singleStyleIconBuiltin'));
    fireEvent.click(screen.getByTestId('single-style-icon-cell'));
    expect(showModal).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId('select-icon-confirm'));

    await waitFor(() => {
      const latest = onStyleChange.mock.calls.at(-1)?.[0];
      expect(latest).toEqual({ showIcon: true, iconKey: 'cc-host' });
    });
    expect(screen.getByTestId('single-style-icon-cell').querySelector('img')?.getAttribute('src')).toBe('/assets/cc-host.svg');

    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));
    await waitFor(() => {
      const latest = onStyleChange.mock.calls.at(-1)?.[0];
      expect(latest).toEqual({ showIcon: true });
      expect(latest.iconKey).toBeUndefined();
      expect(latest.iconImage).toBeUndefined();
    });
    expect(screen.getByTestId('single-style-icon-cell').getAttribute('aria-label')).toBe('dashboard.singleStyleIconUpload');

    const input = screen.getByTestId('single-style-file-input') as HTMLInputElement;
    expect(input.style.display).toBe('none');
    fireEvent.change(input, {
      target: { files: [new File(['icon'], 'mark.png', { type: 'image/png' })] },
    });

    await waitFor(() => {
      const latest = onStyleChange.mock.calls.at(-1)?.[0] as SingleValueStyleConfig;
      expect(latest.iconSource).toBe('upload');
      expect(latest.iconImage?.startsWith('data:image/png')).toBe(true);
      expect(latest.iconKey).toBeUndefined();
    });

    fireEvent.click(sourceRadio('dashboard.singleStyleIconBuiltin'));
    await waitFor(() => {
      expect(screen.getByTestId('single-style-icon-cell').querySelector('img')?.getAttribute('src')).toBe('/assets/cc-host.svg');
      expect(onStyleChange.mock.calls.at(-1)?.[0]).toEqual({ showIcon: true, iconKey: 'cc-host' });
    });
    expect(screen.queryByTestId('single-style-file-input')).toBeNull();

    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));
    await waitFor(() => {
      const latest = onStyleChange.mock.calls.at(-1)?.[0] as SingleValueStyleConfig;
      expect(latest.iconSource).toBe('upload');
      expect(latest.iconImage?.startsWith('data:image/png')).toBe(true);
      expect(latest.iconKey).toBeUndefined();
    });
  });

  it('does not carry an unpersisted icon key onto the next card', async () => {
    const onStyleChange = vi.fn();
    const view = render(<Harness itemId="card-a" onStyleChange={onStyleChange} />);

    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));
    fireEvent.click(screen.getByTestId('single-style-icon-cell'));
    fireEvent.click(screen.getByTestId('select-icon-confirm'));
    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));

    await waitFor(() => {
      expect(onStyleChange.mock.calls.at(-1)?.[0]).toEqual({ showIcon: true });
    });

    view.rerender(<Harness itemId="card-b" onStyleChange={onStyleChange} />);

    await waitFor(() => {
      expect(screen.getByText('dashboard.singleStyleIconBuiltin').closest('label')?.className)
        .toContain('ant-radio-button-wrapper-checked');
      expect(screen.getByTestId('single-style-icon-cell').querySelector('img')).toBeNull();
    });

    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));
    fireEvent.click(sourceRadio('dashboard.singleStyleIconBuiltin'));
    fireEvent.click(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }));

    await waitFor(() => {
      expect(onStyleChange.mock.calls.at(-1)?.[0]).toEqual({
        showIcon: true,
        align: 'center',
      });
    });
    expect(screen.getByTestId('single-style-icon-cell').querySelector('img')).toBeNull();
  });

  it('accepts an empty-type image with a known extension and rejects a disallowed mime', async () => {
    const onStyleChange = vi.fn();
    const warning = vi.spyOn(message, 'warning').mockImplementation(() => ({}) as never);
    render(<Harness onStyleChange={onStyleChange} />);

    fireEvent.click(screen.getByRole('switch', { name: 'dashboard.singleStyleIcon' }));
    fireEvent.click(sourceRadio('dashboard.singleStyleIconUpload'));

    fireEvent.change(screen.getByTestId('single-style-file-input'), {
      target: { files: [new File(['<html></html>'], 'mark.svg', { type: 'text/html' })] },
    });
    expect(warning).toHaveBeenCalledWith('dashboard.singleStyleUploadTypeError');
    expect(onStyleChange.mock.calls.some((call) => call[0]?.iconImage)).toBe(false);

    fireEvent.change(screen.getByTestId('single-style-file-input'), {
      target: { files: [new File(['icon'], 'mark.webp', { type: '' })] },
    });
    await waitFor(() => {
      const latest = onStyleChange.mock.calls.at(-1)?.[0] as SingleValueStyleConfig;
      expect(latest.iconSource).toBe('upload');
      expect(latest.iconImage?.startsWith('data:image/webp')).toBe(true);
    });
    warning.mockRestore();
  });

  it('writes alignment only after a button is pressed', () => {
    const onStyleChange = vi.fn();
    render(<Harness onStyleChange={onStyleChange} />);

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }));
    expect(onStyleChange).toHaveBeenCalledWith({ align: 'center' });
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignCenter' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByRole('button', { name: 'dashboard.singleStyleAlignLeft' }).getAttribute('aria-pressed')).toBe('false');
  });
});
