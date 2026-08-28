'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { RelationshipsProvider } from '@/app/cmdb/context/relationships';
import NetworkTopo from '@/app/cmdb/(pages)/assetData/detail/relationships/networkTopo';
import ApplicationResourceOverview from '@/app/cmdb/(pages)/assetData/detail/relationships/applicationResourceOverview';
import K8sResourceDetailsContent from '@/app/cmdb/(pages)/assetData/detail/k8sResources/K8sResourceDetailsContent';
import IpamMatrix from '@/app/cmdb/(pages)/assetData/detail/ipView/ipamMatrix';
import RoomFloorPlan from '@/app/cmdb/(pages)/assetData/detail/relationships/roomFloorPlan';
import RackElevation from '@/app/cmdb/(pages)/assetData/detail/relationships/rackElevation';
import DeviceDetailDrawer from '@/app/cmdb/(pages)/assetData/detail/relationships/deviceDetailDrawer';
import type { RackDevice } from '@/app/cmdb/types/rackRoom';
import type { ViewFocus, ViewType } from '../viewTypes';
import { resolveRackRoomMode } from '../viewEligibility';
import { buildBaseInfoPath } from '../viewUrls';
import type { NetworkTopoHop } from '@/app/cmdb/(pages)/assetData/detail/relationships/networkTopo/hopDepth';
import usePermissions from '@/hooks/usePermissions';
import {
  RACK_ROOM_ASSET_PERMISSION_PATH,
  canUnplaceFromLayout,
  hasInstanceOperate,
} from '@/app/cmdb/(pages)/assetData/detail/relationships/rackRoomEdit';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';

export interface ViewCanvasHostProps {
  viewType: ViewType;
  focus: ViewFocus;
  focuses?: ViewFocus[];
  /** Shell focus updater — wired to NetworkTopo onRequestFocus when viewType is network. */
  onFocusChange?: (focus: ViewFocus) => void;
  /**
   * Called when the user drills from a room floor plan into a rack while
   * staying in the views hub. Shell should stash the room focus for Back.
   */
  onRoomRackDrill?: (rack: {
    inst_uuid: string;
    inst_name?: string;
    fromRoom: ViewFocus;
  }) => void;
  /** When returning to a room, scroll/highlight this rack on the floor plan. */
  highlightRackId?: string | null;
  /** Optional override; when set, skips built-in view canvases. */
  children?: React.ReactNode;
  networkCenterHop?: NetworkTopoHop;
  onNetworkCenterHopChange?: (hop: NetworkTopoHop) => void;
}

/**
 * Host for primary-view canvases.
 * Embeds detail-view components with local providers where needed.
 */
const ViewCanvasHost: React.FC<ViewCanvasHostProps> = ({
  viewType,
  focus,
  focuses,
  onFocusChange,
  onRoomRackDrill,
  highlightRackId,
  children,
  networkCenterHop,
  onNetworkCenterHopChange,
}) => {
  const { t } = useTranslation();
  const rackFocuses = focuses?.length ? focuses : [focus];
  const rackFocusKey = rackFocuses.map((item) => item.inst_uuid).join(',');
  const [device, setDevice] = useState<RackDevice | null>(null);
  const [deviceRackUuid, setDeviceRackUuid] = useState<string | null>(null);
  const [devOpen, setDevOpen] = useState(false);
  const [rackNonce, setRackNonce] = useState(0);
  const { hasPermission } = usePermissions(RACK_ROOM_ASSET_PERMISSION_PATH);
  const hasEdit = hasPermission(['Edit']);

  // Close hub device drawer when switching rack / mode / view.
  useEffect(() => {
    setDevice(null);
    setDeviceRackUuid(null);
    setDevOpen(false);
  }, [viewType, focus.model_id, focus.mode, rackFocusKey]);

  const handleNetworkRequestFocus = useCallback(
    (payload: { modelId: string; instUuid: string; instName?: string }) => {
      onFocusChange?.({
        model_id: payload.modelId,
        inst_uuid: payload.instUuid,
        inst_name: payload.instName,
      });
    },
    [onFocusChange]
  );

  const handleNetworkViewDetail = useCallback(
    (payload: { modelId: string; instUuid: string; instName?: string }) => {
      window.open(
        buildBaseInfoPath({
          model_id: payload.modelId,
          inst_uuid: payload.instUuid,
          inst_name: payload.instName,
        }),
        '_blank',
        'noopener,noreferrer'
      );
    },
    []
  );

  const handleRackSelect = useCallback(
    (rack: { inst_uuid?: string; inst_id?: string; inst_name?: string }) => {
      const rackUuid = resolveCmdbInstUuid(rack.inst_uuid);
      if (!rackUuid) {
        message.warning('机柜缺少合法 inst_uuid，请先完成 UUID 存量清洗');
        return;
      }
      onRoomRackDrill?.({
        inst_uuid: rackUuid,
        inst_name: rack.inst_name,
        fromRoom: {
          model_id: focus.model_id,
          inst_uuid: focus.inst_uuid,
          inst_name: focus.inst_name,
          model_name: focus.model_name,
          icn: focus.icn,
          mode: 'room',
        },
      });
      onFocusChange?.({
        model_id: 'rack',
        inst_uuid: rackUuid,
        inst_name: rack.inst_name,
        mode: 'rack',
      });
    },
    [onFocusChange, onRoomRackDrill, focus]
  );

  if (children) {
    return <div className="h-full min-h-0 overflow-hidden">{children}</div>;
  }

  if (viewType === 'network') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <RelationshipsProvider>
          <NetworkTopo
            key={focus.inst_uuid}
            modelId={focus.model_id}
            instUuid={focus.inst_uuid}
            fillContainer
            centerHop={networkCenterHop}
            onCenterHopChange={onNetworkCenterHopChange}
            onRequestFocus={handleNetworkRequestFocus}
            onViewDetail={handleNetworkViewDetail}
          />
        </RelationshipsProvider>
      </div>
    );
  }

  if (viewType === 'application') {
    return (
      <div className="h-full min-h-0 overflow-auto">
        <ApplicationResourceOverview
          modelId={focus.model_id}
          instUuid={focus.inst_uuid}
          fillContainer
        />
      </div>
    );
  }

  if (viewType === 'k8s') {
    return (
      <div className="h-[calc(100%+2rem)] w-[calc(100%+2rem)] min-h-0 -m-4 overflow-hidden">
        <K8sResourceDetailsContent instUuid={focus.inst_uuid} />
      </div>
    );
  }

  if (viewType === 'ip') {
    return (
      <div className="h-full min-h-0 overflow-auto">
        <IpamMatrix instUuid={focus.inst_uuid} />
      </div>
    );
  }

  if (viewType === 'rack-room') {
    const rackMode =
      resolveRackRoomMode(focus.model_id, focus.mode) ?? focus.mode ?? 'room';

    if (rackMode === 'rack') {
      const compare = rackFocuses.length > 1;
      const openDevice = (d: RackDevice, rackUuid: string) => {
        setDevice(d);
        setDeviceRackUuid(rackUuid);
        setDevOpen(true);
      };
      return (
        <div className="h-full min-h-0 overflow-x-auto overflow-y-auto">
          <div
            className={
              compare
                ? 'flex items-end gap-6 min-h-full w-max px-2 pb-2'
                : undefined
            }
          >
            {rackFocuses.map((item) => (
              <div
                key={item.inst_uuid}
                className={compare ? 'shrink-0 flex flex-col justify-end' : undefined}
              >
                {compare && (
                  <div className="mb-2 flex items-center justify-center gap-2 px-1">
                    <span className="max-w-[280px] truncate text-sm font-medium text-[var(--color-text-1)]">
                      {item.inst_name || item.inst_uuid}
                    </span>
                    <Button
                      type="link"
                      size="small"
                      className="px-0"
                      onClick={() => window.open(
                        buildBaseInfoPath(item),
                        '_blank',
                        'noopener,noreferrer'
                      )}
                    >
                      {t('ViewsHub.viewDetail')}
                    </Button>
                  </div>
                )}
                <RackElevation
                  key={`${item.inst_uuid}-${rackNonce}`}
                  modelId={item.model_id}
                  instUuid={item.inst_uuid}
                  embedded={compare}
                  compare={compare}
                  onDeviceClick={(d) => openDevice(d, item.inst_uuid)}
                />
              </div>
            ))}
          </div>
          <DeviceDetailDrawer
            device={device}
            open={devOpen}
            onClose={() => setDevOpen(false)}
            containerInstUuid={deviceRackUuid || focus.inst_uuid}
            canUnplace={canUnplaceFromLayout({
              hasEdit,
              instOperate: hasInstanceOperate(device?.permission),
            })}
            onUnplaced={() => setRackNonce((n) => n + 1)}
          />
        </div>
      );
    }

    return (
      <div className="h-full min-h-0 overflow-auto">
        <RoomFloorPlan
          modelId={focus.model_id}
          instUuid={focus.inst_uuid}
          onRackSelect={handleRackSelect}
          highlightRackId={highlightRackId || undefined}
        />
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex items-center justify-center text-[var(--color-text-3)]">
      {t('ViewsHub.workspacePlaceholder')}
    </div>
  );
};

export default ViewCanvasHost;
