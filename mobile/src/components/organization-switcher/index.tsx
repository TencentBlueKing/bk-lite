'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { usePathname, useRouter } from 'next/navigation';
import { Switch } from 'antd-mobile';
import { CheckOutline, RightOutline, TeamOutline } from 'antd-mobile-icons';
import MobileSearchBar from '@/components/mobile-search-bar';
import { useAuth } from '@/context/auth';
import { MODULE_ROOTS, moduleForPath } from '@/platform/availability/model';
import {
  collectGroupIds,
  filterGroupTree,
  type OrganizationGroup,
} from '@/utils/organization';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.css';

function OrganizationTree({
  groups,
  depth,
  currentTeamId,
  expandedIds,
  onToggle,
  onSelect,
}: {
  groups: OrganizationGroup[];
  depth: number;
  currentTeamId: string | null;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (group: OrganizationGroup) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul className={styles.tree} role={depth === 0 ? 'tree' : 'group'}>
      {groups.map((group) => {
        const hasChildren = Boolean(group.subGroups?.length);
        const expanded = expandedIds.has(group.id);
        const selected = group.id === currentTeamId;

        return (
          <li key={group.id} role="treeitem" aria-expanded={hasChildren ? expanded : undefined} aria-selected={selected}>
            <div
              className={`${styles.row} ${selected ? styles.rowSelected : ''}`}
              style={{ '--org-depth': depth } as CSSProperties}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className={styles.expandButton}
                  aria-label={expanded ? t('organization.collapse') : t('organization.expand')}
                  onClick={() => onToggle(group.id)}
                >
                  <RightOutline className={`${styles.expandIcon} ${expanded ? styles.expandIconOpen : ''}`} aria-hidden />
                </button>
              ) : (
                <span className={styles.expandSpacer} aria-hidden />
              )}
              <button
                type="button"
                className={styles.rowButton}
                onClick={() => onSelect(group)}
              >
                <span className={styles.rowName}>{group.name}</span>
                {selected ? <CheckOutline className={styles.rowCheck} aria-hidden /> : null}
              </button>
            </div>
            {hasChildren && expanded ? (
              <OrganizationTree
                groups={group.subGroups || []}
                depth={depth + 1}
                currentTeamId={currentTeamId}
                expandedIds={expandedIds}
                onToggle={onToggle}
                onSelect={onSelect}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export default function OrganizationSwitcher({
  variant = 'header',
}: {
  variant?: 'header' | 'inline';
} = {}) {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = usePathname();
  const {
    currentTeamId,
    currentTeamName,
    includeChildren,
    groupTree,
    applyOrganizationScope,
  } = useAuth();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [panelTop, setPanelTop] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [draftTeamId, setDraftTeamId] = useState<string | null>(currentTeamId);
  const [draftTeamName, setDraftTeamName] = useState<string | null>(currentTeamName);
  const [draftIncludeChildren, setDraftIncludeChildren] = useState(includeChildren);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(collectGroupIds(groupTree)));

  const visibleTree = useMemo(
    () => filterGroupTree(groupTree, keyword),
    [groupTree, keyword],
  );

  useEffect(() => {
    if (!open) return;
    setKeyword('');
    setExpandedIds(new Set(collectGroupIds(groupTree)));
    setDraftTeamId(currentTeamId);
    setDraftTeamName(currentTeamName);
    setDraftIncludeChildren(includeChildren);
  }, [groupTree, open, currentTeamId, currentTeamName, includeChildren]);

  useEffect(() => {
    if (!keyword.trim()) return;
    setExpandedIds(new Set(collectGroupIds(visibleTree)));
  }, [keyword, visibleTree]);

  const label = currentTeamName || t('organization.select');
  const canOpen = groupTree.length > 0;

  const close = useCallback(() => setOpen(false), []);

  const navigateToModuleRoot = useCallback(() => {
    const moduleKey = moduleForPath(pathname || '') ?? 'profile';
    const root = MODULE_ROOTS[moduleKey];
    if (pathname !== root) {
      router.replace(root);
    }
  }, [pathname, router]);

  const commitAndClose = useCallback(() => {
    const changed = applyOrganizationScope({
      teamId: draftTeamId || groupTree[0]?.id || '',
      teamName: draftTeamName || undefined,
      includeChildren: draftIncludeChildren,
    });
    close();
    if (changed) navigateToModuleRoot();
  }, [
    applyOrganizationScope,
    close,
    draftIncludeChildren,
    draftTeamId,
    draftTeamName,
    groupTree,
    navigateToModuleRoot,
  ]);

  useLayoutEffect(() => {
    if (!open) return;

    const updatePanelTop = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      // 一级顶栏：贴在 header 底边；「我的」inline：贴在触发行底边，避免落到安全区下盖住身份区
      const header = trigger.closest('header');
      if (header) {
        setPanelTop(header.getBoundingClientRect().bottom);
        return;
      }
      setPanelTop(trigger.getBoundingClientRect().bottom);
    };

    updatePanelTop();
    window.addEventListener('resize', updatePanelTop);
    window.addEventListener('scroll', updatePanelTop, true);
    window.visualViewport?.addEventListener('resize', updatePanelTop);
    window.visualViewport?.addEventListener('scroll', updatePanelTop);
    return () => {
      window.removeEventListener('resize', updatePanelTop);
      window.removeEventListener('scroll', updatePanelTop, true);
      window.visualViewport?.removeEventListener('resize', updatePanelTop);
      window.visualViewport?.removeEventListener('scroll', updatePanelTop);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') commitAndClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [commitAndClose, open]);

  const handleSelect = (group: OrganizationGroup) => {
    setDraftTeamId(group.id);
    setDraftTeamName(group.name);
  };

  const handleIncludeChildren = (checked: boolean) => {
    setDraftIncludeChildren(checked);
  };

  const overlayStyle = {
    '--org-panel-top': panelTop > 0 ? `${panelTop}px` : undefined,
  } as CSSProperties;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`${variant === 'inline' ? styles.triggerInline : styles.trigger} ${open ? styles.triggerOpen : ''}`}
        aria-label={t('organization.switch')}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={label}
        disabled={!canOpen}
        onClick={() => {
          if (!canOpen) return;
          if (open) commitAndClose();
          else setOpen(true);
        }}
      >
        {variant === 'inline' ? (
          <>
            <span className={styles.triggerInlineName}>{label}</span>
            <RightOutline className={styles.triggerInlineChevron} aria-hidden />
          </>
        ) : (
          <span className={styles.pill}>
            <TeamOutline className={styles.triggerIcon} aria-hidden />
            <span className={styles.triggerName}>{label}</span>
            <span className={`${styles.caret} ${open ? styles.caretOpen : ''}`} aria-hidden />
          </span>
        )}
      </button>
      {open && typeof document !== 'undefined'
        ? createPortal(
          <div className={styles.overlay} style={overlayStyle}>
            <button
              type="button"
              className={styles.mask}
              aria-label={t('common.close')}
              onClick={commitAndClose}
            />
            <div
              className={styles.panel}
              role="dialog"
              aria-label={t('organization.switch')}
            >
              <div className={styles.search}>
                <MobileSearchBar
                  value={keyword}
                  onChange={setKeyword}
                  placeholder={t('organization.search')}
                />
              </div>
              <div className={styles.toolbar}>
                <span className={styles.includeLabel}>{t('organization.includeSubgroups')}</span>
                <Switch
                  checked={draftIncludeChildren}
                  onChange={handleIncludeChildren}
                  className={styles.includeSwitch}
                />
              </div>
              <div className={styles.treeScroll}>
                {visibleTree.length > 0 ? (
                  <OrganizationTree
                    groups={visibleTree}
                    depth={0}
                    currentTeamId={draftTeamId}
                    expandedIds={expandedIds}
                    onToggle={(id) => {
                      setExpandedIds((current) => {
                        const next = new Set(current);
                        if (next.has(id)) next.delete(id);
                        else next.add(id);
                        return next;
                      });
                    }}
                    onSelect={handleSelect}
                  />
                ) : (
                  <p className={styles.empty}>{t('organization.empty')}</p>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )
        : null}
    </>
  );
}
