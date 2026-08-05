"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  DeleteOutlined,
  FolderAddOutlined,
  FolderOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Descriptions,
  Empty,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Spin,
  Tag,
  Tooltip,
  Tree,
  Typography,
  message,
} from "antd";
import type { DataNode as TreeDataNode } from "antd/lib/tree";
import { useWikiApi } from "@/app/opspilot/api/wiki";
import PermissionWrapper from "@/components/permission";
import usePermissions from "@/hooks/usePermissions";
import type {
  WikiExistingDirectoryRef,
  WikiExistingStructureDirectory,
  WikiFrozenStructureDirectory,
  WikiNewDirectoryRef,
  WikiNewStructureDirectory,
  WikiStructureParentRef,
  WikiStructureReadResult,
  WikiStructureSaveDirectory,
  WikiStructureSaveRequest,
} from "@/app/opspilot/types/wiki";
import { HandledRequestError } from "@/utils/request";
import { useTranslation } from "@/utils/i18n";
import WikiDirectoryImpactDrawer from "./WikiDirectoryImpactDrawer";

const UNCLASSIFIED_DIRECTORY_KEY = "__unclassified__";
const ROOT_PARENT_KEY = "root";
const EXISTING_KEY_PREFIX = "existing:";
const NEW_KEY_PREFIX = "new:";
const MAX_DIRECTORY_DEPTH = 8;
const DIRECTORY_ORIGINS = new Set(["system", "schema", "manual"]);
const DIRECTORY_STATUSES = new Set(["active", "retired", "merged", "archived"]);

let draftSequence = 0;

interface ConflictState {
  code?: string;
  details?: unknown;
  latest: WikiStructureReadResult | null;
  loadingLatest: boolean;
  latestError: boolean;
}

interface StructureConflictDiff {
  pageTypesChanged: boolean;
  localOnly: string[];
  latestOnly: string[];
  changed: string[];
}

const normalizeStructureText = (value: string): string =>
  value.normalize("NFKC").replace(/\s+/gu, " ").trim().toLocaleLowerCase();

const uniqueTexts = (values: string[]): string[] => {
  const identities = new Set<string>();
  return values.reduce<string[]>((result, value) => {
    const displayValue = value.trim();
    const identity = normalizeStructureText(displayValue);
    if (!identity || identities.has(identity)) return result;
    identities.add(identity);
    result.push(displayValue);
    return result;
  }, []);
};

const directoryKey = (directory: WikiStructureSaveDirectory): string =>
  directory.kind === "existing"
    ? EXISTING_KEY_PREFIX + directory.id
    : NEW_KEY_PREFIX + directory.client_ref;

const parentKey = (parent: WikiStructureParentRef): string | null => {
  if (!parent) return null;
  return "id" in parent
    ? EXISTING_KEY_PREFIX + parent.id
    : NEW_KEY_PREFIX + parent.client_ref;
};

const directoryParentRef = (
  directory: WikiStructureSaveDirectory,
): WikiExistingDirectoryRef | WikiNewDirectoryRef =>
  directory.kind === "existing"
    ? { id: directory.id, key: directory.key }
    : { client_ref: directory.client_ref };

const isUnclassifiedDirectory = (
  directory?: WikiStructureSaveDirectory,
): boolean =>
  directory?.kind === "existing" &&
  directory.origin === "system" &&
  directory.key === UNCLASSIFIED_DIRECTORY_KEY;
const isActiveDirectory = (directory?: WikiStructureSaveDirectory): boolean =>
  Boolean(
    directory && (directory.kind === "new" || directory.status === "active"),
  );

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isCanonicalDirectoryRef = (
  value: unknown,
): value is WikiExistingDirectoryRef =>
  isRecord(value) &&
  Number.isInteger(value.id) &&
  typeof value.key === "string";

const isCanonicalFrozenDirectory = (
  value: unknown,
): value is WikiFrozenStructureDirectory => {
  if (!isRecord(value) || !isRecord(value.rules)) return false;
  const parentIsCanonical =
    Object.prototype.hasOwnProperty.call(value, "parent") &&
    (value.parent === null || isCanonicalDirectoryRef(value.parent));
  return (
    Number.isInteger(value.id) &&
    typeof value.key === "string" &&
    typeof value.origin === "string" &&
    DIRECTORY_ORIGINS.has(value.origin) &&
    typeof value.status === "string" &&
    DIRECTORY_STATUSES.has(value.status) &&
    typeof value.name === "string" &&
    typeof value.description === "string" &&
    Number.isInteger(value.order) &&
    Array.isArray(value.rules.allowed_page_types) &&
    value.rules.allowed_page_types.every(
      (pageType) => typeof pageType === "string",
    ) &&
    Array.isArray(value.rules.default_for_page_types) &&
    value.rules.default_for_page_types.every(
      (pageType) => typeof pageType === "string",
    ) &&
    parentIsCanonical
  );
};

const toEditableDirectory = (
  directory: WikiFrozenStructureDirectory,
): WikiExistingStructureDirectory => ({
  kind: "existing",
  id: directory.id,
  key: directory.key,
  origin: directory.origin,
  status: directory.status,
  name: directory.name,
  description: directory.description,
  order: directory.order,
  rules: {
    allowed_page_types: [...directory.rules.allowed_page_types],
    default_for_page_types: [...directory.rules.default_for_page_types],
  },
  parent: directory.parent ? { ...directory.parent } : null,
});
const parseReadStructure = (structure: unknown) => {
  if (!isRecord(structure)) {
    return { pageTypes: [], directories: [], isCanonical: false };
  }

  const rawPageTypes = structure.page_types;
  const pageTypesAreCanonical =
    Array.isArray(rawPageTypes) &&
    rawPageTypes.every((pageType) => typeof pageType === "string");
  const pageTypes = pageTypesAreCanonical ? uniqueTexts(rawPageTypes) : [];
  const rawDirectories = Array.isArray(structure.directories)
    ? structure.directories
    : [];
  const canonicalDirectories = rawDirectories.filter(
    isCanonicalFrozenDirectory,
  );
  const directoriesAreCanonical =
    Array.isArray(structure.directories) &&
    canonicalDirectories.length === rawDirectories.length;

  return {
    pageTypes,
    directories: canonicalDirectories.map(toEditableDirectory),
    isCanonical:
      structure.format_version === 1 &&
      pageTypesAreCanonical &&
      directoriesAreCanonical,
  };
};

const toSaveDirectory = (
  directory: WikiStructureSaveDirectory,
): WikiStructureSaveDirectory => {
  const fields = {
    name: directory.name.trim(),
    description: directory.description.trim(),
    order: directory.order,
    rules: {
      allowed_page_types: [...directory.rules.allowed_page_types],
      default_for_page_types: [...directory.rules.default_for_page_types],
    },
    parent: directory.parent ? { ...directory.parent } : null,
  };

  if (directory.kind === "existing") {
    return {
      kind: "existing",
      id: directory.id,
      key: directory.key,
      origin: directory.origin,
      status: directory.status,
      ...fields,
    };
  }

  return {
    kind: "new",
    client_ref: directory.client_ref,
    ...fields,
  };
};

const createClientRef = (): string => {
  draftSequence += 1;
  return "draft-" + Date.now() + "-" + draftSequence;
};

const conflictDetailsText = (details: unknown): string => {
  if (typeof details === "string") return details;
  if (details === null || details === undefined) return "";
  try {
    return JSON.stringify(details);
  } catch {
    return "";
  }
};

interface WikiStructureEditorProps {
  kbId: number;
  embedded?: boolean;
}

const WikiStructureEditor: React.FC<WikiStructureEditorProps> = ({
  kbId,
  embedded = false,
}) => {
  const { t } = useTranslation();
  const { fetchWikiStructure, saveWikiStructure } = useWikiApi();
  const { hasPermission } = usePermissions();
  const [structureRevision, setStructureRevision] =
    useState<WikiStructureReadResult["structure_revision"]>(null);
  const [activeGeneration, setActiveGeneration] =
    useState<WikiStructureReadResult["active_generation"]>(null);
  const [pageTypes, setPageTypes] = useState<string[]>([]);
  const [directories, setDirectories] = useState<WikiStructureSaveDirectory[]>(
    [],
  );
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [structureIsCanonical, setStructureIsCanonical] = useState(false);
  const [impactDrawerOpen, setImpactDrawerOpen] = useState(false);

  const installReadResult = useCallback(
    (result: WikiStructureReadResult, preferredKey?: string | null) => {
      const parsedStructure = parseReadStructure(result.structure);
      const editableDirectories = parsedStructure.directories;
      setStructureRevision(result.structure_revision);
      setActiveGeneration(result.active_generation);
      setPageTypes(parsedStructure.pageTypes);
      setDirectories(editableDirectories);
      setStructureIsCanonical(parsedStructure.isCanonical);
      setSelectedKey((currentKey) => {
        const candidateKey = preferredKey ?? currentKey;
        if (
          candidateKey &&
          editableDirectories.some(
            (directory) => directoryKey(directory) === candidateKey,
          )
        ) {
          return candidateKey;
        }
        const firstEditable = editableDirectories.find(
          (directory) => !isUnclassifiedDirectory(directory),
        );
        return firstEditable
          ? directoryKey(firstEditable)
          : editableDirectories[0]
            ? directoryKey(editableDirectories[0])
            : null;
      });
      setDirty(false);
      setValidationError("");
      setConflict(null);
      setLoaded(true);
    },
    [],
  );

  const loadStructure = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    try {
      const result = await fetchWikiStructure(kbId);
      installReadResult(result);
    } catch (error) {
      setLoadFailed(true);
      if (!(error instanceof HandledRequestError)) {
        message.error(t("wiki.structureLoadFailed"));
      }
    } finally {
      setLoading(false);
    }
    // useWikiApi 返回的函数随 render 重建；请求只按 kbId 重载。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [installReadResult, kbId, t]);

  useEffect(() => {
    void loadStructure();
  }, [loadStructure]);

  const nodeMap = useMemo(
    () =>
      new Map(
        directories.map((directory) => [directoryKey(directory), directory]),
      ),
    [directories],
  );
  const operationDirectories = useMemo(
    () =>
      directories.filter(
        (directory): directory is WikiExistingStructureDirectory =>
          directory.kind === "existing",
      ),
    [directories],
  );

  const childrenByParent = useMemo(() => {
    const result = new Map<string | null, WikiStructureSaveDirectory[]>();
    directories.forEach((directory) => {
      const key = parentKey(directory.parent);
      const children = result.get(key) ?? [];
      children.push(directory);
      result.set(key, children);
    });
    result.forEach((children) => {
      children.sort(
        (left, right) =>
          left.order - right.order || left.name.localeCompare(right.name),
      );
    });
    return result;
  }, [directories]);

  const selectedDirectory = selectedKey ? nodeMap.get(selectedKey) : undefined;
  const hasWritableSnapshot = Boolean(structureRevision && activeGeneration);
  const canWrite =
    hasPermission(["Edit"]) && hasWritableSnapshot && structureIsCanonical;
  const selectedIsSystem = isUnclassifiedDirectory(selectedDirectory);
  const selectedLocked = !canWrite || selectedIsSystem;
  const selectedHasChildren = Boolean(
    selectedKey && childrenByParent.get(selectedKey)?.length,
  );

  const descendantKeys = useMemo(() => {
    if (!selectedKey) return new Set<string>();
    const descendants = new Set<string>();
    const pending = [...(childrenByParent.get(selectedKey) ?? [])];
    while (pending.length) {
      const directory = pending.pop();
      if (!directory) continue;
      const key = directoryKey(directory);
      if (descendants.has(key)) continue;
      descendants.add(key);
      pending.push(...(childrenByParent.get(key) ?? []));
    }
    return descendants;
  }, [childrenByParent, selectedKey]);

  const treeData = useMemo<TreeDataNode[]>(() => {
    const buildNodes = (
      currentParentKey: string | null,
      ancestors: Set<string>,
    ): TreeDataNode[] =>
      (childrenByParent.get(currentParentKey) ?? []).map((directory) => {
        const key = directoryKey(directory);
        const hasCycle = ancestors.has(key);
        const nextAncestors = new Set(ancestors);
        nextAncestors.add(key);
        return {
          key,
          icon: isUnclassifiedDirectory(directory) ? (
            <InboxOutlined />
          ) : (
            <FolderOutlined />
          ),
          title: (
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate">
                {directory.name || t("wiki.structureUnnamedDirectory")}
              </span>
              {directory.kind === "new" && (
                <Tag bordered={false}>{t("wiki.structureNewTag")}</Tag>
              )}
            </div>
          ),
          children: hasCycle ? undefined : buildNodes(key, nextAncestors),
        };
      });
    return buildNodes(null, new Set<string>());
  }, [childrenByParent, t]);

  const parentOptions = useMemo(() => {
    const options = [
      { value: ROOT_PARENT_KEY, label: t("wiki.structureRoot") },
    ];
    directories.forEach((directory) => {
      const key = directoryKey(directory);
      if (
        key === selectedKey ||
        descendantKeys.has(key) ||
        isUnclassifiedDirectory(directory)
      )
        return;
      if (!isActiveDirectory(directory)) return;
      const identity =
        directory.kind === "existing" ? directory.key : directory.client_ref;
      options.push({
        value: key,
        label: directory.name + " · " + identity,
      });
    });
    return options;
  }, [descendantKeys, directories, selectedKey, t]);

  const markChanged = () => {
    setDirty(true);
    setValidationError("");
  };

  const updateSelected = (
    updater: (
      directory: WikiStructureSaveDirectory,
    ) => WikiStructureSaveDirectory,
  ) => {
    if (!selectedKey || !selectedDirectory || selectedLocked) return;
    setDirectories((current) =>
      current.map((directory) =>
        directoryKey(directory) === selectedKey
          ? updater(directory)
          : directory,
      ),
    );
    markChanged();
  };

  const handlePageTypesChange = (values: string[]) => {
    if (!canWrite) return;
    const nextPageTypes = uniqueTexts(values);
    const domain = new Set(nextPageTypes.map(normalizeStructureText));
    setPageTypes(nextPageTypes);
    setDirectories((current) =>
      current.map((directory) => {
        if (isUnclassifiedDirectory(directory)) return directory;
        const allowedPageTypes = directory.rules.allowed_page_types.filter(
          (pageType) => domain.has(normalizeStructureText(pageType)),
        );
        const allowedPageTypeDomain = new Set(
          allowedPageTypes.map(normalizeStructureText),
        );
        return {
          ...directory,
          rules: {
            allowed_page_types: allowedPageTypes,
            default_for_page_types:
              directory.rules.default_for_page_types.filter((pageType) => {
                const identity = normalizeStructureText(pageType);
                return (
                  domain.has(identity) && allowedPageTypeDomain.has(identity)
                );
              }),
          },
        };
      }),
    );
    markChanged();
  };

  const addDirectory = (parent: WikiStructureSaveDirectory | null) => {
    if (
      !canWrite ||
      (parent &&
        (!isActiveDirectory(parent) || isUnclassifiedDirectory(parent)))
    )
      return;
    const parentRef = parent ? directoryParentRef(parent) : null;
    const parentIdentity = parentKey(parentRef);
    const siblingOrders = directories
      .filter((directory) => parentKey(directory.parent) === parentIdentity)
      .map((directory) => directory.order);
    const directory: WikiNewStructureDirectory = {
      kind: "new",
      client_ref: createClientRef(),
      name: t("wiki.structureNewDirectory"),
      description: "",
      order: Math.max(-10, ...siblingOrders) + 10,
      rules: {
        allowed_page_types: [...pageTypes],
        default_for_page_types: [],
      },
      parent: parentRef,
    };
    setDirectories((current) => [...current, directory]);
    setSelectedKey(directoryKey(directory));
    markChanged();
  };

  const deleteSelected = () => {
    if (
      !selectedKey ||
      !selectedDirectory ||
      selectedLocked ||
      selectedHasChildren
    )
      return;
    const nextDirectories = directories.filter(
      (directory) => directoryKey(directory) !== selectedKey,
    );
    const nextParentKey = parentKey(selectedDirectory.parent);
    setDirectories(nextDirectories);
    setSelectedKey(
      nextParentKey &&
        nextDirectories.some(
          (directory) => directoryKey(directory) === nextParentKey,
        )
        ? nextParentKey
        : nextDirectories[0]
          ? directoryKey(nextDirectories[0])
          : null,
    );
    markChanged();
  };

  const validateStructure = (): string | null => {
    if (!structureRevision || !activeGeneration)
      return t("wiki.structureNoActiveGeneration");
    if (!pageTypes.length) return t("wiki.structureValidationPageTypes");
    const normalizedPageTypes = pageTypes.map(normalizeStructureText);
    if (normalizedPageTypes.some((pageType) => !pageType)) {
      return t("wiki.structureValidationPageTypes");
    }
    if (new Set(normalizedPageTypes).size !== normalizedPageTypes.length) {
      return t("wiki.structureValidationDuplicatePageTypes");
    }
    if (!directories.length || !directories.some(isUnclassifiedDirectory)) {
      return t("wiki.structureValidationSystemDirectory");
    }

    const pageTypeDomain = new Set(normalizedPageTypes);
    const siblingNames = new Set<string>();
    const defaultOwners = new Map<string, string>();
    for (const directory of directories) {
      const normalizedName = normalizeStructureText(directory.name);
      if (!normalizedName) return t("wiki.structureValidationName");
      if (!Number.isInteger(directory.order) || directory.order < 0) {
        return t("wiki.structureValidationOrder");
      }

      const currentParentKey = parentKey(directory.parent);
      const parentDirectory = currentParentKey
        ? nodeMap.get(currentParentKey)
        : undefined;
      if (currentParentKey && !parentDirectory) {
        return t("wiki.structureValidationParent");
      }
      if (
        isActiveDirectory(directory) &&
        parentDirectory &&
        !isActiveDirectory(parentDirectory)
      ) {
        return t("wiki.structureValidationInactiveParent");
      }

      if (isActiveDirectory(directory)) {
        const siblingIdentity =
          (currentParentKey ?? ROOT_PARENT_KEY) + ":" + normalizedName;
        if (siblingNames.has(siblingIdentity)) {
          return t("wiki.structureValidationDuplicateName");
        }
        siblingNames.add(siblingIdentity);
      }

      const allowedIdentities = directory.rules.allowed_page_types.map(
        normalizeStructureText,
      );
      const defaultIdentities = directory.rules.default_for_page_types.map(
        normalizeStructureText,
      );
      const allowed = new Set(allowedIdentities);
      const rulesAreUnique =
        allowed.size === allowedIdentities.length &&
        new Set(defaultIdentities).size === defaultIdentities.length;
      const rulesInDomain = [...allowedIdentities, ...defaultIdentities].every(
        (pageType) => pageTypeDomain.has(pageType),
      );
      const defaultsAllowed = defaultIdentities.every((pageType) =>
        allowed.has(pageType),
      );
      if (!rulesAreUnique || !rulesInDomain || !defaultsAllowed) {
        return t("wiki.structureValidationRules");
      }

      if (isActiveDirectory(directory)) {
        const owner = directoryKey(directory);
        for (const pageType of defaultIdentities) {
          if (
            defaultOwners.has(pageType) &&
            defaultOwners.get(pageType) !== owner
          ) {
            return t("wiki.structureValidationDuplicateDefault");
          }
          defaultOwners.set(pageType, owner);
        }
      }
    }

    for (const directory of directories) {
      let current: WikiStructureSaveDirectory | undefined = directory;
      let depth = 0;
      const visited = new Set<string>();
      while (current) {
        const key = directoryKey(current);
        if (visited.has(key)) return t("wiki.structureValidationCycle");
        visited.add(key);
        depth += 1;
        if (depth > MAX_DIRECTORY_DEPTH)
          return t("wiki.structureValidationDepth");
        const currentParentKey = parentKey(current.parent);
        if (!currentParentKey) break;
        current = nodeMap.get(currentParentKey);
        if (!current) return t("wiki.structureValidationParent");
      }
    }

    return null;
  };

  const handleSave = async () => {
    if (!canWrite) return;
    const errorMessage = validateStructure();
    if (errorMessage) {
      setValidationError(errorMessage);
      return;
    }
    if (!structureRevision || !activeGeneration) return;

    const selectedBeforeSave = selectedKey;
    const payload: WikiStructureSaveRequest = {
      structure_version: structureRevision.version,
      base_generation_id: activeGeneration.id,
      structure: {
        format_version: 1,
        page_types: [...pageTypes],
        directories: directories.map(toSaveDirectory),
      },
    };

    setSaving(true);
    setConflict(null);
    try {
      const result = await saveWikiStructure(kbId, payload);
      let preferredKey = selectedBeforeSave;
      if (preferredKey?.startsWith(NEW_KEY_PREFIX)) {
        const clientRef = preferredKey.slice(NEW_KEY_PREFIX.length);
        const mapping = result.client_ref_map.find(
          (item) => item.client_ref === clientRef,
        );
        preferredKey = mapping ? EXISTING_KEY_PREFIX + mapping.id : null;
      }
      installReadResult(
        {
          structure_revision: result.structure_revision,
          active_generation: result.active_generation,
          structure: result.structure,
        },
        preferredKey,
      );
      setLoadFailed(false);
      message.success(t("wiki.structureSaved"));
    } catch (error) {
      if (error instanceof HandledRequestError && error.status === 409) {
        setConflict({
          code: error.code,
          details: error.details,
          latest: null,
          loadingLatest: true,
          latestError: false,
        });
        try {
          const latest = await fetchWikiStructure(kbId);
          setConflict((current) =>
            current
              ? {
                ...current,
                latest,
                loadingLatest: false,
                latestError: false,
              }
              : current,
          );
        } catch {
          setConflict((current) =>
            current
              ? { ...current, loadingLatest: false, latestError: true }
              : current,
          );
        }
      } else if (!(error instanceof HandledRequestError)) {
        message.error(t("wiki.structureSaveFailed"));
      }
    } finally {
      setSaving(false);
    }
  };

  const conflictDetail = useMemo(
    () => conflictDetailsText(conflict?.details),
    [conflict?.details],
  );
  const conflictLatestStructure = useMemo(
    () =>
      conflict?.latest ? parseReadStructure(conflict.latest.structure) : null,
    [conflict?.latest],
  );
  const conflictDiff = useMemo<StructureConflictDiff | null>(() => {
    if (!conflictLatestStructure) return null;
    const localDirectories = new Map(
      directories.map((directory) => [directoryKey(directory), directory]),
    );
    const latestDirectories = new Map(
      conflictLatestStructure.directories.map((directory) => [
        directoryKey(directory),
        directory,
      ]),
    );
    const comparable = (directory: WikiStructureSaveDirectory) =>
      JSON.stringify(toSaveDirectory(directory));
    return {
      pageTypesChanged:
        JSON.stringify(pageTypes) !==
        JSON.stringify(conflictLatestStructure.pageTypes),
      localOnly: Array.from(localDirectories.entries())
        .filter(([key]) => !latestDirectories.has(key))
        .map(([, directory]) => directory.name),
      latestOnly: Array.from(latestDirectories.entries())
        .filter(([key]) => !localDirectories.has(key))
        .map(([, directory]) => directory.name),
      changed: Array.from(localDirectories.entries())
        .filter(([key, directory]) => {
          const latestDirectory = latestDirectories.get(key);
          return latestDirectory
            ? comparable(directory) !== comparable(latestDirectory)
            : false;
        })
        .map(([, directory]) => directory.name),
    };
  }, [conflictLatestStructure, directories, pageTypes]);

  const canUseConflictLatest = Boolean(
    conflict?.latest?.structure_revision &&
    conflict.latest.active_generation &&
    conflictLatestStructure?.isCanonical,
  );

  const refreshConflictLatest = async () => {
    if (!conflict) return;
    setConflict((current) =>
      current
        ? { ...current, loadingLatest: true, latestError: false }
        : current,
    );
    try {
      const latest = await fetchWikiStructure(kbId);
      setConflict((current) =>
        current
          ? { ...current, latest, loadingLatest: false, latestError: false }
          : current,
      );
    } catch {
      setConflict((current) =>
        current
          ? { ...current, loadingLatest: false, latestError: true }
          : current,
      );
    }
  };

  const handleReapplyLocalDraft = () => {
    const latest = conflict?.latest;
    if (
      !latest?.structure_revision ||
      !latest.active_generation ||
      !conflictLatestStructure?.isCanonical
    )
      return;
    setStructureRevision(latest.structure_revision);
    setActiveGeneration(latest.active_generation);
    setStructureIsCanonical(true);
    setConflict(null);
    setValidationError("");
    setDirty(true);
    message.info(t("wiki.structureConflictReapplied"));
  };

  const handleDiscardLocalDraft = () => {
    if (!conflict?.latest) return;
    installReadResult(conflict.latest);
    setLoadFailed(false);
    message.info(t("wiki.structureConflictDiscarded"));
  };

  if (!loaded && loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center">
        <Spin />
      </div>
    );
  }

  if (!loaded && loadFailed) {
    return (
      <Alert
        showIcon
        type="error"
        message={t("wiki.structureLoadFailed")}
        action={
          <Button onClick={() => void loadStructure()}>
            {t("wiki.structureRetry")}
          </Button>
        }
      />
    );
  }

  const parentValue = selectedDirectory
    ? (parentKey(selectedDirectory.parent) ?? ROOT_PARENT_KEY)
    : ROOT_PARENT_KEY;
  let defaultPageTypeOptions: string[] = [];
  if (selectedDirectory) {
    defaultPageTypeOptions = pageTypes.filter((pageType) => {
      const pageTypeIdentity = normalizeStructureText(pageType);
      return selectedDirectory.rules.allowed_page_types.some(
        (allowedPageType) =>
          normalizeStructureText(allowedPageType) === pageTypeIdentity,
      );
    });
  }
  const deleteDisabledReason = selectedIsSystem
    ? t("wiki.structureSystemLocked")
    : selectedHasChildren
      ? t("wiki.structureDeleteHasChildren")
      : !hasWritableSnapshot
        ? t("wiki.structureNoActiveGeneration")
        : !structureIsCanonical
          ? t("wiki.structureCanonicalReadOnly")
          : "";

  return (
    <Spin spinning={loading}>
      <div className="space-y-4">
        <section
          className={
            embedded
              ? ""
              : "rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4"
          }
        >
          <div
            className={`flex flex-wrap items-start gap-3 ${
              embedded ? "justify-end" : "mb-4 justify-between"
            }`}
          >
            {!embedded && (
              <div>
                <h3 className="m-0 text-base font-semibold text-[var(--color-text-1)]">
                  {t("wiki.settingsStructure")}
                </h3>
                <p className="mb-0 mt-1 text-[13px] leading-6 text-[var(--color-text-3)]">
                  {t("wiki.structureEditorDesc")}
                </p>
              </div>
            )}
            <div className="flex items-center gap-2">
              {dirty ? (
                <Popconfirm
                  title={t("wiki.structureDiscardRefreshConfirm")}
                  onConfirm={() => void loadStructure()}
                >
                  <Button
                    icon={<ReloadOutlined />}
                    disabled={loading || saving}
                  >
                    {t("wiki.structureRefresh")}
                  </Button>
                </Popconfirm>
              ) : (
                <Button
                  icon={<ReloadOutlined />}
                  disabled={loading || saving}
                  onClick={() => void loadStructure()}
                >
                  {t("wiki.structureRefresh")}
                </Button>
              )}
              <PermissionWrapper requiredPermissions={["Edit"]}>
                <Button
                  disabled={!canWrite || dirty || loading || saving}
                  onClick={() => setImpactDrawerOpen(true)}
                >
                  {t("wiki.directoryGovernance")}
                </Button>
              </PermissionWrapper>
              <PermissionWrapper requiredPermissions={["Edit"]}>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  loading={saving}
                  disabled={!dirty || !canWrite || Boolean(conflict)}
                  onClick={() => void handleSave()}
                >
                  {t("wiki.structureSave")}
                </Button>
              </PermissionWrapper>
            </div>
          </div>
          {!embedded && (
            <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
              <Descriptions.Item label={t("wiki.structureVersion")}>
                <span className="tabular-nums">
                  {structureRevision?.version ?? "--"}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label={t("wiki.structureBaseGeneration")}>
                <span className="tabular-nums">
                  {activeGeneration?.id ?? "--"}
                </span>
                {activeGeneration && (
                  <Tag className="ml-2">{activeGeneration.status}</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t("wiki.structureFingerprint")}>
                {structureRevision?.fingerprint ? (
                  <Typography.Text
                    copyable={{ text: structureRevision.fingerprint }}
                    className="break-all font-mono text-xs"
                  >
                    {structureRevision.fingerprint}
                  </Typography.Text>
                ) : (
                  "--"
                )}
              </Descriptions.Item>
            </Descriptions>
          )}
        </section>

        {!embedded && (
          <Alert
            showIcon
            type="info"
            message={t("wiki.structureTruthTitle")}
            description={t("wiki.structureTruthDesc")}
          />
        )}
        {loadFailed && (
          <Alert
            showIcon
            type="error"
            message={t("wiki.structureRefreshFailed")}
            action={
              <Button onClick={() => void loadStructure()}>
                {t("wiki.structureRetry")}
              </Button>
            }
          />
        )}

        {!hasWritableSnapshot && (
          <Alert
            showIcon
            type="warning"
            message={t("wiki.structureNoActiveGeneration")}
            description={t("wiki.structureNoActiveGenerationDesc")}
          />
        )}
        {!structureIsCanonical && (
          <Alert
            showIcon
            type="warning"
            message={t("wiki.structureCanonicalReadOnly")}
            description={t("wiki.structureCanonicalReadOnlyDesc")}
          />
        )}

        {conflict && (
          <Alert
            showIcon
            type="warning"
            message={t("wiki.structureConflictTitle")}
            description={
              <div className="space-y-3">
                <div>{t("wiki.structureConflictDesc")}</div>
                {conflict.code && (
                  <div>
                    <span className="text-[var(--color-text-3)]">
                      {t("wiki.structureConflictCode")}:{" "}
                    </span>
                    <Typography.Text code>{conflict.code}</Typography.Text>
                  </div>
                )}
                {conflictDetail && (
                  <Typography.Text
                    copyable={{ text: conflictDetail }}
                    className="break-all text-xs"
                  >
                    {conflictDetail}
                  </Typography.Text>
                )}
                {conflict.loadingLatest && (
                  <div className="flex items-center gap-2 text-xs text-[var(--color-text-3)]">
                    <Spin size="small" />
                    {t("wiki.structureConflictLoadingLatest")}
                  </div>
                )}
                {conflict.latestError && (
                  <Alert
                    type="error"
                    showIcon
                    message={t("wiki.structureConflictLatestFailed")}
                    action={
                      <Button
                        size="small"
                        onClick={() => void refreshConflictLatest()}
                      >
                        {t("wiki.structureRetry")}
                      </Button>
                    }
                  />
                )}
                {conflict.latest && conflictLatestStructure && (
                  <>
                    <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                      <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                        <div className="mb-1 font-medium">
                          {t("wiki.structureConflictLocalDraft")}
                        </div>
                        <div className="text-xs text-[var(--color-text-3)]">
                          v{structureRevision?.version ?? "--"} · Generation{" "}
                          {activeGeneration?.id ?? "--"}
                        </div>
                        <div className="mt-1 text-xs">
                          {t("wiki.structurePageTypes")}: {pageTypes.length} ·{" "}
                          {t("wiki.structureDirectories")}: {directories.length}
                        </div>
                      </div>
                      <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                        <div className="mb-1 font-medium">
                          {t("wiki.structureConflictLatest")}
                        </div>
                        <div className="text-xs text-[var(--color-text-3)]">
                          v{conflict.latest.structure_revision?.version ?? "--"}{" "}
                          · Generation{" "}
                          {conflict.latest.active_generation?.id ?? "--"}
                        </div>
                        <div className="mt-1 text-xs">
                          {t("wiki.structurePageTypes")}:{" "}
                          {conflictLatestStructure.pageTypes.length} ·{" "}
                          {t("wiki.structureDirectories")}:{" "}
                          {conflictLatestStructure.directories.length}
                        </div>
                      </div>
                    </div>
                    <div className="rounded border border-dashed border-[var(--color-border)] p-3 text-xs">
                      <div className="mb-2 font-medium text-[var(--color-text-2)]">
                        {t("wiki.structureConflictDiff")}
                      </div>
                      {conflictDiff &&
                      !conflictDiff.pageTypesChanged &&
                      !conflictDiff.localOnly.length &&
                      !conflictDiff.latestOnly.length &&
                      !conflictDiff.changed.length ? (
                        <span className="text-[var(--color-text-3)]">
                          {t("wiki.structureConflictNoDiff")}
                        </span>
                        ) : (
                        <div className="space-y-1 text-[var(--color-text-2)]">
                          {conflictDiff?.pageTypesChanged && (
                            <div>
                              {t("wiki.structureConflictPageTypesChanged")}
                            </div>
                          )}
                          {!!conflictDiff?.localOnly.length && (
                            <div>
                              {t("wiki.structureConflictLocalOnly")}:{" "}
                              {conflictDiff.localOnly.join("、")}
                            </div>
                          )}
                          {!!conflictDiff?.latestOnly.length && (
                            <div>
                              {t("wiki.structureConflictLatestOnly")}:{" "}
                              {conflictDiff.latestOnly.join("、")}
                            </div>
                          )}
                          {!!conflictDiff?.changed.length && (
                            <div>
                              {t("wiki.structureConflictChanged")}:{" "}
                              {conflictDiff.changed.join("、")}
                            </div>
                          )}
                        </div>
                        )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="primary"
                        disabled={!canUseConflictLatest}
                        onClick={handleReapplyLocalDraft}
                      >
                        {t("wiki.structureConflictReapply")}
                      </Button>
                      <Popconfirm
                        title={t("wiki.structureConflictDiscardConfirm")}
                        disabled={!canUseConflictLatest}
                        onConfirm={handleDiscardLocalDraft}
                      >
                        <Button disabled={!canUseConflictLatest}>
                          {t("wiki.structureConflictDiscard")}
                        </Button>
                      </Popconfirm>
                    </div>
                  </>
                )}
              </div>
            }
          />
        )}

        {validationError && (
          <Alert
            showIcon
            type="error"
            message={t("wiki.structureValidationTitle")}
            description={validationError}
          />
        )}

        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
            {t("wiki.structurePageTypes")}
          </div>
          <p className="mb-3 mt-0 text-[13px] leading-6 text-[var(--color-text-3)]">
            {t("wiki.structurePageTypesTip")}
          </p>
          <Select
            mode="tags"
            value={pageTypes}
            disabled={!canWrite}
            status={pageTypes.length ? undefined : "error"}
            placeholder={t("wiki.structurePageTypesPlaceholder")}
            tokenSeparators={[",", "，"]}
            options={pageTypes.map((pageType) => ({
              value: pageType,
              label: pageType,
            }))}
            className="w-full"
            aria-label={t("wiki.structurePageTypes")}
            onChange={handlePageTypesChange}
          />
        </section>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <section className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] xl:col-span-1">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
              <div className="text-sm font-medium text-[var(--color-text-1)]">
                {t("wiki.structureDirectories")}
              </div>
              <div className="flex items-center gap-1">
                <PermissionWrapper requiredPermissions={["Edit"]}>
                  <Tooltip title={t("wiki.structureAddRoot")}>
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      disabled={!canWrite}
                      aria-label={t("wiki.structureAddRoot")}
                      onClick={() => addDirectory(null)}
                    />
                  </Tooltip>
                </PermissionWrapper>
                <PermissionWrapper requiredPermissions={["Edit"]}>
                  <Tooltip
                    title={
                      selectedIsSystem
                        ? t("wiki.structureSystemLocked")
                        : !isActiveDirectory(selectedDirectory)
                          ? t("wiki.structureInactiveParent")
                          : t("wiki.structureAddChild")
                    }
                  >
                    <Button
                      size="small"
                      icon={<FolderAddOutlined />}
                      disabled={
                        !canWrite ||
                        !selectedDirectory ||
                        selectedIsSystem ||
                        !isActiveDirectory(selectedDirectory)
                      }
                      aria-label={t("wiki.structureAddChild")}
                      onClick={() =>
                        selectedDirectory && addDirectory(selectedDirectory)
                      }
                    />
                  </Tooltip>
                </PermissionWrapper>
              </div>
            </div>
            <div className="min-h-[360px] p-2">
              {treeData.length ? (
                <Tree
                  blockNode
                  showIcon
                  defaultExpandAll
                  selectedKeys={selectedKey ? [selectedKey] : []}
                  treeData={treeData}
                  className="bg-transparent [&_.ant-tree-node-content-wrapper]:min-w-0 [&_.ant-tree-title]:block [&_.ant-tree-title]:min-w-0 [&_.ant-tree-treenode]:w-full"
                  onSelect={(keys) => {
                    if (keys.length) setSelectedKey(String(keys[0]));
                  }}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("wiki.structureEmpty")}
                />
              )}
            </div>
          </section>

          <section className="min-w-0 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4 xl:col-span-2">
            {!selectedDirectory ? (
              <div className="flex min-h-[360px] items-center justify-center">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("wiki.structureNoSelection")}
                />
              </div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-2 text-sm font-semibold text-[var(--color-text-1)]">
                      {selectedDirectory.name ||
                        t("wiki.structureUnnamedDirectory")}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {selectedDirectory.kind === "existing" ? (
                        <>
                          <Tag>
                            {t("wiki.structureId")}: {selectedDirectory.id}
                          </Tag>
                          <Tag>
                            {t("wiki.structureKey")}: {selectedDirectory.key}
                          </Tag>
                          <Tag>
                            {t("wiki.structureOrigin")}:{" "}
                            {selectedDirectory.origin}
                          </Tag>
                          <Tag>
                            {t("wiki.structureStatus")}:{" "}
                            {selectedDirectory.status}
                          </Tag>
                        </>
                      ) : (
                        <Tag>
                          {t("wiki.structureClientRef")}:{" "}
                          {selectedDirectory.client_ref}
                        </Tag>
                      )}
                    </div>
                  </div>
                  <PermissionWrapper requiredPermissions={["Edit"]}>
                    <Tooltip
                      title={deleteDisabledReason || t("wiki.structureDelete")}
                    >
                      <span>
                        <Popconfirm
                          disabled={Boolean(deleteDisabledReason)}
                          title={t("wiki.structureDeleteConfirm")}
                          onConfirm={deleteSelected}
                        >
                          <Button
                            danger
                            icon={<DeleteOutlined />}
                            disabled={Boolean(deleteDisabledReason)}
                            aria-label={t("wiki.structureDelete")}
                          >
                            {t("wiki.structureDelete")}
                          </Button>
                        </Popconfirm>
                      </span>
                    </Tooltip>
                  </PermissionWrapper>
                </div>

                {selectedIsSystem && (
                  <Alert
                    showIcon
                    type="warning"
                    message={t("wiki.structureSystemLocked")}
                  />
                )}

                <div className="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-2">
                  <div>
                    <label
                      htmlFor="wiki-structure-name"
                      className="mb-2 block text-sm font-medium text-[var(--color-text-1)]"
                    >
                      {t("wiki.structureName")}
                    </label>
                    <Input
                      id="wiki-structure-name"
                      value={selectedDirectory.name}
                      disabled={selectedLocked}
                      maxLength={255}
                      onChange={(event) =>
                        updateSelected((directory) => ({
                          ...directory,
                          name: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                      {t("wiki.structureParent")}
                    </div>
                    <Select
                      value={parentValue}
                      disabled={selectedLocked}
                      options={parentOptions}
                      className="w-full"
                      aria-label={t("wiki.structureParent")}
                      onChange={(value: string) => {
                        const nextParent =
                          value === ROOT_PARENT_KEY
                            ? null
                            : nodeMap.get(value)
                              ? directoryParentRef(
                                  nodeMap.get(
                                    value,
                                  ) as WikiStructureSaveDirectory,
                              )
                              : null;
                        updateSelected((directory) => ({
                          ...directory,
                          parent: nextParent,
                        }));
                      }}
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label
                      htmlFor="wiki-structure-description"
                      className="mb-2 block text-sm font-medium text-[var(--color-text-1)]"
                    >
                      {t("wiki.structureDescription")}
                    </label>
                    <Input.TextArea
                      id="wiki-structure-description"
                      value={selectedDirectory.description}
                      disabled={selectedLocked}
                      autoSize={{ minRows: 3, maxRows: 8 }}
                      maxLength={2000}
                      showCount
                      onChange={(event) =>
                        updateSelected((directory) => ({
                          ...directory,
                          description: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                      {t("wiki.structureOrder")}
                    </div>
                    <InputNumber
                      value={selectedDirectory.order}
                      disabled={selectedLocked}
                      min={0}
                      precision={0}
                      className="w-full"
                      aria-label={t("wiki.structureOrder")}
                      onChange={(value) =>
                        updateSelected((directory) => ({
                          ...directory,
                          order: typeof value === "number" ? value : 0,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                      {t("wiki.structureAllowedPageTypes")}
                    </div>
                    <Select
                      mode="multiple"
                      value={selectedDirectory.rules.allowed_page_types}
                      disabled={selectedLocked}
                      options={pageTypes.map((pageType) => ({
                        value: pageType,
                        label: pageType,
                      }))}
                      className="w-full"
                      aria-label={t("wiki.structureAllowedPageTypes")}
                      onChange={(values: string[]) =>
                        updateSelected((directory) => {
                          const allowedPageTypes = uniqueTexts(values);
                          const allowedPageTypeDomain = new Set(
                            allowedPageTypes.map(normalizeStructureText),
                          );
                          return {
                            ...directory,
                            rules: {
                              allowed_page_types: allowedPageTypes,
                              default_for_page_types:
                                directory.rules.default_for_page_types.filter(
                                  (pageType) =>
                                    allowedPageTypeDomain.has(
                                      normalizeStructureText(pageType),
                                    ),
                                ),
                            },
                          };
                        })
                      }
                    />
                  </div>
                  <div className="md:col-span-2">
                    <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                      {t("wiki.structureDefaultPageTypes")}
                    </div>
                    <p className="mb-2 mt-0 text-[13px] leading-6 text-[var(--color-text-3)]">
                      {t("wiki.structureDefaultPageTypesTip")}
                    </p>
                    <Select
                      mode="multiple"
                      value={selectedDirectory.rules.default_for_page_types}
                      disabled={selectedLocked}
                      options={defaultPageTypeOptions.map((pageType) => ({
                        value: pageType,
                        label: pageType,
                      }))}
                      className="w-full"
                      aria-label={t("wiki.structureDefaultPageTypes")}
                      onChange={(values: string[]) =>
                        updateSelected((directory) => ({
                          ...directory,
                          rules: {
                            ...directory.rules,
                            default_for_page_types: uniqueTexts(values),
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
      <WikiDirectoryImpactDrawer
        open={impactDrawerOpen}
        kbId={kbId}
        structureVersion={structureRevision?.version ?? null}
        baseGenerationId={activeGeneration?.id ?? null}
        directories={operationDirectories}
        onClose={() => setImpactDrawerOpen(false)}
        onCompleted={() => loadStructure()}
      />
    </Spin>
  );
};

export default WikiStructureEditor;
