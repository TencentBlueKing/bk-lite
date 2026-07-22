'use client';

import NodeManagerCollectorPackageModal, {
  type NodeManagerCollectorPackageModalProps,
} from '@/app/node-manager/components/node-manager-collector-package-modal';
import useNodeManagerApi from '@/app/node-manager/api';

type CollectorPackageModalRuntimeProps = Omit<
  NodeManagerCollectorPackageModalProps,
  | 'addCollectorAction'
  | 'editCollectorAction'
  | 'uploadPackageAction'
  | 'getControllerListAction'
>;

const CollectorPackageModalRuntime = (
  props: CollectorPackageModalRuntimeProps,
) => {
  const {
    addCollector,
    editCollecttor,
    uploadPackage,
    getControllerList,
  } = useNodeManagerApi();

  return (
    <NodeManagerCollectorPackageModal
      {...props}
      addCollectorAction={addCollector}
      editCollectorAction={editCollecttor}
      uploadPackageAction={uploadPackage}
      getControllerListAction={getControllerList}
    />
  );
};

export default CollectorPackageModalRuntime;
