'use client';

import React, { useCallback, useEffect, useState } from 'react';
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

export interface ViewCanvasHostProps {
  viewType: ViewType;
  focus: ViewFocus;
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
}

/**
 * Host for primary-view canvases.
 * Embeds detail-view components with local providers where needed.
 */
const ViewCanvasHost: React.FC<ViewCanvasHostProps> = ({
  viewType,
  focus,
  onFocusChange,
  onRoomRackDrill,
  highlightRackId,
  children,
}) => {
  const { t } = useTranslation();
  const [device, setDevice] = useState<RackDevice | null>(null);
  const [devOpen, setDevOpen] = useState(false);

  // Close hub device drawer when switching rack / mode / view.
  useEffect(() => {
    setDevice(null);
    setDevOpen(false);
  }, [viewType, focus.model_id, focus.inst_uuid, focus.mode]);

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
      const rackUuid = rack.inst_uuid || rack.inst_id || '';
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
            modelId={focus.model_id}
            instUuid={focus.inst_uuid}
            fillContainer
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
        />
      </div>
    );
  }

  if (viewType === 'k8s') {
    return (
      <div className="h-full min-h-0 overflow-hidden">
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
      return (
        <div className="h-full min-h-0 overflow-auto">
          <RackElevation
            modelId={focus.model_id}
            instUuid={focus.inst_uuid}
            onDeviceClick={(d) => {
              setDevice(d);
              setDevOpen(true);
            }}
          />
          <DeviceDetailDrawer
            device={device}
            open={devOpen}
            onClose={() => setDevOpen(false)}
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
