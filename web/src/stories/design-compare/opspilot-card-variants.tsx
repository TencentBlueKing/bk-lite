'use client';

/**
 * Visual-only card option board for picking a direction.
 * Labels are codes only (A–F), no prose.
 */

import { useState, type CSSProperties, type ReactNode } from 'react';
import { Dropdown, Tooltip, Typography } from 'antd';
import {
  MoreOutlined,
  PushpinFilled,
  PushpinOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';
import { afterSys, resolveMetaTagTone } from './opspilot-after-system';

const { Text, Paragraph } = Typography;

export type CardLook = 'A' | 'B' | 'C' | 'D' | 'E' | 'F';

const sample = {
  name: 'Incident Copilot',
  description: '协调告警处置、审批跟进与变更回滚，覆盖生产值班主路径。',
  icon: 'jiqirenjiaohukapian',
  meta: ['Pilot', 'gpt-4o'],
  owner: 'admin',
  team: 'SRE',
  updatedAt: '12m 前',
  pinned: true,
  online: true,
};

function StatusTime({ online, time }: { online: boolean; time: string }) {
  return (
    <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          height: 20,
          padding: '0 8px',
          borderRadius: 999,
          fontSize: 11,
          color: afterSys.text2,
          background: afterSys.fill,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: online ? afterSys.success : afterSys.text4,
          }}
        />
        {online ? 'Online' : 'Offline'}
      </span>
      <span style={{ fontSize: 12, color: afterSys.text3 }}>{time}</span>
    </div>
  );
}

function MetaRow({ items }: { items: string[] }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {items.map((m) => {
        const tone = resolveMetaTagTone(m);
        return (
          <span
            key={m}
            style={{
              height: 20,
              padding: '0 7px',
              borderRadius: afterSys.radiusSm,
              fontSize: 11,
              fontWeight: 500,
              color: tone.color,
              background: tone.background,
              display: 'inline-flex',
              alignItems: 'center',
            }}
          >
            {m}
          </span>
        );
      })}
    </div>
  );
}

function Footer() {
  return (
    <div
      style={{
        paddingTop: 10,
        borderTop: afterSys.divider,
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        fontSize: 12,
      }}
    >
      <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ color: afterSys.text4 }}>Owner</span>
        <span style={{ margin: '0 6px', color: afterSys.text4 }}>·</span>
        <span style={{ color: afterSys.text2 }}>{sample.owner}</span>
      </div>
      <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: 'right' }}>
        <span style={{ color: afterSys.text4 }}>Team</span>
        <span style={{ margin: '0 6px', color: afterSys.text4 }}>·</span>
        <span style={{ color: afterSys.text2 }}>{sample.team}</span>
      </div>
    </div>
  );
}

function Actions({
  pinned,
  tone = 'default',
}: {
  pinned: boolean;
  tone?: 'default' | 'onWash';
}) {
  const color = tone === 'onWash' ? afterSys.text2 : afterSys.text3;
  return (
    <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
      <button
        type="button"
        aria-label="pin"
        style={{
          width: 28,
          height: 28,
          border: 'none',
          borderRadius: afterSys.radiusSm,
          background: 'transparent',
          color: pinned ? afterSys.primary : color,
          cursor: 'pointer',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        {pinned ? <PushpinFilled style={{ fontSize: 12 }} /> : <PushpinOutlined style={{ fontSize: 12 }} />}
      </button>
      <Dropdown menu={{ items: [{ key: 'edit', label: '编辑' }] }} trigger={['click']}>
        <button
          type="button"
          aria-label="more"
          style={{
            width: 28,
            height: 28,
            border: 'none',
            borderRadius: afterSys.radiusSm,
            background: 'transparent',
            color,
            cursor: 'pointer',
            display: 'grid',
            placeItems: 'center',
          }}
        >
          <MoreOutlined />
        </button>
      </Dropdown>
    </div>
  );
}

function Shell({
  children,
  style,
}: {
  children: ReactNode;
  style?: CSSProperties;
}) {
  const [hover, setHover] = useState(false);
  return (
    <article
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? afterSys.hover : afterSys.bg,
        border: afterSys.border,
        borderRadius: afterSys.radius,
        overflow: 'hidden',
        height: 'auto',
        display: 'flex',
        flexDirection: 'column',
        minHeight: 0,
        ...style,
      }}
    >
      {children}
    </article>
  );
}

function Body({
  iconBg,
  actions,
}: {
  iconBg?: string;
  actions?: ReactNode;
}) {
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '14px 14px 0' }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: afterSys.radiusSm,
            background: iconBg || afterSys.fill,
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
          }}
        >
          <Icon type={sample.icon} className="text-xl" style={{ color: afterSys.primary }} />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Tooltip title={sample.name}>
            <Text
              strong
              style={{
                display: 'block',
                fontSize: 14,
                color: afterSys.text1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {sample.name}
            </Text>
          </Tooltip>
          <StatusTime online={sample.online} time={sample.updatedAt} />
        </div>
        {actions}
      </div>
      <div style={{ padding: '10px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
        <Paragraph style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: afterSys.text2 }} ellipsis={{ rows: 2 }}>
          {sample.description}
        </Paragraph>
        <MetaRow items={sample.meta} />
        <Footer />
      </div>
    </>
  );
}

/** A — flat */
function LookA() {
  return (
    <Shell>
      <Body actions={<Actions pinned={sample.pinned} />} />
    </Shell>
  );
}

/** B — whole-card soft wash */
function LookB() {
  return (
    <Shell
      style={{
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--color-primary, #155aef) 4%, var(--color-bg, #fff)) 0%, var(--color-bg, #fff) 42%)',
      }}
    >
      <Body actions={<Actions pinned={sample.pinned} />} />
    </Shell>
  );
}

/** C — left accent rail */
function LookC() {
  return (
    <Shell style={{ position: 'relative' }}>
      <div
        aria-hidden
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: afterSys.primary,
        }}
      />
      <div style={{ paddingLeft: 3 }}>
        <Body actions={<Actions pinned={sample.pinned} />} />
      </div>
    </Shell>
  );
}

/** D — tinted icon well only */
function LookD() {
  return (
    <Shell>
      <Body
        iconBg="var(--color-primary-bg-active, #e1edfc)"
        actions={<Actions pinned={sample.pinned} />}
      />
    </Shell>
  );
}

/** E — 2px top hairline */
function LookE() {
  return (
    <Shell>
      <div
        aria-hidden
        style={{
          height: 2,
          background:
            'linear-gradient(90deg, var(--color-primary, #155aef), color-mix(in srgb, var(--color-primary, #155aef) 15%, transparent))',
          flexShrink: 0,
        }}
      />
      <Body actions={<Actions pinned={sample.pinned} />} />
    </Shell>
  );
}

/** F — short strip, icon in body (previous attempt) */
function LookF() {
  return (
    <Shell>
      <div
        style={{
          height: 40,
          background:
            'linear-gradient(120deg, var(--color-bg-image-gradient-1, #e3e8ff) 0%, var(--color-bg-image-gradient-2, #f9fafb) 72%)',
          position: 'relative',
          flexShrink: 0,
        }}
      >
        <div style={{ position: 'absolute', right: 6, top: 6 }}>
          <Actions pinned={sample.pinned} tone="onWash" />
        </div>
        <div style={{ position: 'absolute', left: 8, top: 7, width: 28, height: 28 }} />
      </div>
      <Body />
    </Shell>
  );
}

const LOOKS: { id: CardLook; render: () => ReactNode }[] = [
  { id: 'A', render: () => <LookA /> },
  { id: 'B', render: () => <LookB /> },
  { id: 'C', render: () => <LookC /> },
  { id: 'D', render: () => <LookD /> },
  { id: 'E', render: () => <LookE /> },
  { id: 'F', render: () => <LookF /> },
];

export function OpsPilotCardLookBoard() {
  return (
    <div
      style={{
        padding: 20,
        background: afterSys.page,
        minHeight: '100vh',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: 20,
        alignContent: 'start',
      }}
    >
      {LOOKS.map((look) => (
        <div key={look.id} style={{ display: 'grid', gap: 8 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 999,
              background: afterSys.bg,
              border: afterSys.border,
              color: afterSys.text1,
              fontSize: 13,
              fontWeight: 600,
              display: 'grid',
              placeItems: 'center',
            }}
          >
            {look.id}
          </div>
          <div style={{ minHeight: 260 }}>{look.render()}</div>
        </div>
      ))}
    </div>
  );
}
