## 1. Backend Data Models

- [x] 1.1 Create `server/apps/opspilot/models/memory_mgmt.py` with MemorySpace model (id, name, introduction, scope, write_rule, default_model, team, timestamps)
- [x] 1.2 Add Memory model to `memory_mgmt.py` (id, memory_space FK, owner_username, owner_domain, title, content, timestamps)
- [x] 1.3 Update `server/apps/opspilot/models/__init__.py` to export new models
- [x] 1.4 Create and run database migrations

## 2. Backend API (Memory Space Management)

- [x] 2.1 Create `server/apps/opspilot/serializers/memory_serializer.py` with MemorySpaceSerializer and MemorySerializer
- [x] 2.2 Create `server/apps/opspilot/viewsets/memory_view.py` with MemorySpaceViewSet (CRUD, team filtering)
- [x] 2.3 Add MemoryViewSet to `memory_view.py` with scope-based permission filtering (personal: only creator by username+domain)
- [x] 2.4 Update `server/apps/opspilot/viewsets/__init__.py` to export new viewsets
- [x] 2.5 Register memory_space and memory routes in `server/apps/opspilot/urls.py`
- [x] 2.6 Add operation audit logs for MemorySpace and Memory CRUD operations

## 3. Backend Memory Service

- [x] 3.1 Implement memory write logic in `server/apps/opspilot/tasks.py` as `process_memory_write` Celery task
- [x] 3.2 Implement LLM-based content normalization using write_rule
- [x] 3.3 Implement LLM-based intelligent update/create decision (reads existing memories, decides to merge or create new)
- [x] 3.4 Enhanced merge prompt with detailed rules and examples to ensure proper content merging (not replacement)

## 4. Backend Workflow Nodes

- [x] 4.1 Create `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/` directory
- [x] 4.2 Create `memory_read.py` with MemoryReadNode - implement execute() with scope-based permission check (personal: filter by username+domain)
- [x] 4.3 Create `memory_write.py` with MemoryWriteNode - implement execute() with async task trigger
- [x] 4.4 Create `__init__.py` in memory directory to export executors
- [x] 4.5 Register `memory_read` and `memory_write` in `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`

## 5. Frontend Types and Constants

- [x] 5.1 Add `memory_read` and `memory_write` to NodeType union in `web/src/app/opspilot/components/chatflow/types.ts`
- [x] 5.2 Add MemoryReadNodeConfig and MemoryWriteNodeConfig interfaces to types.ts
- [x] 5.3 Add default configs for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/constants.ts`

## 6. Frontend API Hooks

- [x] 6.1 Create `web/src/app/opspilot/api/memory.ts` with useMemorySpaces, useMemorySpace, useCreateMemorySpace, useUpdateMemorySpace, useDeleteMemorySpace hooks
- [x] 6.2 Add useMemories, useMemory, useUpdateMemory, useDeleteMemory hooks to memory.ts

## 7. Frontend Workflow Node Components

- [x] 7.1 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryReadNode.tsx` wrapping BaseNode
- [x] 7.2 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryWriteNode.tsx` wrapping BaseNode
- [x] 7.3 Export new nodes in `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
- [x] 7.4 Register nodes in nodeTypes in `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`

## 8. Frontend Node Configuration Panels

- [x] 8.1 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryReadConfig.tsx` with memory space selector
- [x] 8.2 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryWriteConfig.tsx` with memory space selector
- [x] 8.3 Export new configs in `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`
- [x] 8.4 Add cases for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx`

## 9. Frontend Memory Management Pages

- [x] 9.1 Create `web/src/app/opspilot/(pages)/memory/page.tsx` - memory space list page with cards
- [x] 9.2 Create memory space create/edit modal component
- [x] 9.3 Create `web/src/app/opspilot/(pages)/memory/[id]/page.tsx` - memory space detail page with memory list
- [x] 9.4 Create memory entry preview/edit component with Markdown support
- [x] 9.5 Add test_write endpoint for testing memory write rules

## 10. Frontend Navigation and i18n

- [x] 10.1 Add "记忆" navigation item to opspilot main navigation menu
- [x] 10.2 Add memory icon to navigation
- [x] 10.3 Add i18n translations for memory module (en.json, zh.json)

## 11. Testing and Verification

- [x] 11.1 Test memory space CRUD via API
- [x] 11.2 Test memory read node execution with personal scope (creator vs non-creator)
- [x] 11.3 Test memory read node execution with team scope
- [x] 11.4 Test memory write node execution with async task
- [x] 11.5 Test memory extraction and merge with LLM
- [x] 11.6 Test frontend memory management pages
- [x] 11.7 Test workflow editor with new nodes
