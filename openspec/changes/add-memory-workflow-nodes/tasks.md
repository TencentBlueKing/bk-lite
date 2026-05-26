## 1. Backend Data Models

- [ ] 1.1 Create `server/apps/opspilot/models/memory_mgmt.py` with MemorySpace model (id, name, description, scope, guidelines, model, team, created_by, timestamps)
- [ ] 1.2 Add Memory model to `memory_mgmt.py` (id, memory_space FK, owner FK nullable, title, content, source_workflow, source_node, timestamps, unique_together constraint)
- [ ] 1.3 Update `server/apps/opspilot/models/__init__.py` to export new models
- [ ] 1.4 Create and run database migrations

## 2. Backend API (Memory Space Management)

- [ ] 2.1 Create `server/apps/opspilot/serializers/memory_serializer.py` with MemorySpaceSerializer and MemorySerializer
- [ ] 2.2 Create `server/apps/opspilot/viewsets/memory_viewset.py` with MemorySpaceViewSet (CRUD, team filtering)
- [ ] 2.3 Add MemoryViewSet to `memory_viewset.py` with scope-based permission filtering (personal: only creator, organization: all team members)
- [ ] 2.4 Update `server/apps/opspilot/viewsets/__init__.py` to export new viewsets
- [ ] 2.5 Register memory_space and memory routes in `server/apps/opspilot/urls.py`

## 3. Backend Memory Service

- [ ] 3.1 Create `server/apps/opspilot/services/memory_service.py` with MemoryService class
- [ ] 3.2 Implement `_extract_memory()` method - LLM-based memory extraction using guidelines
- [ ] 3.3 Implement `_merge_memory()` method - LLM-based memory merging with deduplication
- [ ] 3.4 Implement `write_memory()` method - orchestrates extraction, merge, and save
- [ ] 3.5 Create `server/apps/opspilot/tasks/memory_tasks.py` with `process_memory_write` Celery task

## 4. Backend Workflow Nodes

- [ ] 4.1 Create `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/` directory
- [ ] 4.2 Create `memory_read.py` with MemoryReadExecutor - implement execute() with scope-based permission check
- [ ] 4.3 Create `memory_write.py` with MemoryWriteExecutor - implement execute() with async task trigger
- [ ] 4.4 Create `__init__.py` in memory directory to export executors
- [ ] 4.5 Register `memory_read` and `memory_write` in `server/apps/opspilot/utils/chat_flow_utils/engine/node_registry.py`

## 5. Frontend Types and Constants

- [ ] 5.1 Add `memory_read` and `memory_write` to NodeType union in `web/src/app/opspilot/components/chatflow/types.ts`
- [ ] 5.2 Add MemoryReadNodeConfig and MemoryWriteNodeConfig interfaces to types.ts
- [ ] 5.3 Add default configs for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/constants.ts`

## 6. Frontend API Hooks

- [ ] 6.1 Create `web/src/app/opspilot/api/memory.ts` with useMemorySpaces, useMemorySpace, useCreateMemorySpace, useUpdateMemorySpace, useDeleteMemorySpace hooks
- [ ] 6.2 Add useMemories, useMemory, useUpdateMemory, useDeleteMemory hooks to memory.ts

## 7. Frontend Workflow Node Components

- [ ] 7.1 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryReadNode.tsx` wrapping BaseNode
- [ ] 7.2 Create `web/src/app/opspilot/components/chatflow/nodes/MemoryWriteNode.tsx` wrapping BaseNode
- [ ] 7.3 Export new nodes in `web/src/app/opspilot/components/chatflow/nodes/index.tsx`
- [ ] 7.4 Register nodes in nodeTypes in `web/src/app/opspilot/components/chatflow/ChatflowEditor.tsx`

## 8. Frontend Node Configuration Panels

- [ ] 8.1 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryReadConfig.tsx` with memory space selector
- [ ] 8.2 Create `web/src/app/opspilot/components/chatflow/components/nodeConfigs/MemoryWriteConfig.tsx` with memory space selector
- [ ] 8.3 Export new configs in `web/src/app/opspilot/components/chatflow/components/nodeConfigs/index.ts`
- [ ] 8.4 Add cases for memory_read and memory_write in `web/src/app/opspilot/components/chatflow/NodeConfigForm.tsx`

## 9. Frontend Memory Management Pages

- [ ] 9.1 Create `web/src/app/opspilot/(pages)/memory/page.tsx` - memory space list page with cards
- [ ] 9.2 Create memory space create modal component
- [ ] 9.3 Create `web/src/app/opspilot/(pages)/memory/[id]/layout.tsx` - detail page layout with sidebar
- [ ] 9.4 Create `web/src/app/opspilot/(pages)/memory/[id]/page.tsx` - redirect to config
- [ ] 9.5 Create `web/src/app/opspilot/(pages)/memory/[id]/config/page.tsx` - configuration view
- [ ] 9.6 Create `web/src/app/opspilot/(pages)/memory/[id]/list/page.tsx` - memory entries list view
- [ ] 9.7 Create memory entry preview/edit component with Markdown support
- [ ] 9.8 Create `web/src/app/opspilot/context/memoryContext.tsx` for state management

## 10. Frontend Navigation

- [ ] 10.1 Add "记忆" navigation item to opspilot main navigation menu
- [ ] 10.2 Add memory icon to navigation

## 11. Testing and Verification

- [ ] 11.1 Test memory space CRUD via API
- [ ] 11.2 Test memory read node execution with personal scope (creator vs non-creator)
- [ ] 11.3 Test memory read node execution with organization scope
- [ ] 11.4 Test memory write node execution with async task
- [ ] 11.5 Test memory extraction and merge with LLM
- [ ] 11.6 Test frontend memory management pages
- [ ] 11.7 Test workflow editor with new nodes
