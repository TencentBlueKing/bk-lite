"""
Tests for Memory Workflow Nodes (MemoryRead and MemoryWrite).

Based on OpenSpec: openspec/changes/add-memory-workflow-nodes/specs/memory-workflow-nodes/spec.md

Scenarios covered:
- MemoryRead: passthrough, personal scope (creator/non-creator), team scope, no config, empty memory
- MemoryWrite: passthrough, async task trigger, permission check, empty input, no config
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub out optional C-extension modules
# ---------------------------------------------------------------------------
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.models.memory_mgmt import Memory, MemorySpace  # noqa: E402
from apps.opspilot.utils.chat_flow_utils.nodes.memory.memory_read import MemoryReadNode  # noqa: E402
from apps.opspilot.utils.chat_flow_utils.nodes.memory.memory_write import MemoryWriteNode  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memory_space_team(db):
    """Create a team-scope MemorySpace."""
    return MemorySpace.objects.create(
        name="Team Knowledge Base",
        introduction="Shared team memories",
        team=[1],
        scope=MemorySpace.SCOPE_TEAM,
        write_rule="Extract key facts",
        default_model="gpt-4o",
        created_by="admin",
        domain="test.com",
    )


@pytest.fixture
def memory_space_personal(db):
    """Create a personal-scope MemorySpace."""
    return MemorySpace.objects.create(
        name="Personal Notes",
        introduction="Personal memories",
        team=[1],
        scope=MemorySpace.SCOPE_PERSONAL,
        write_rule="",
        default_model="",
        created_by="alice",
        domain="test.com",
    )


@pytest.fixture
def team_memories(memory_space_team):
    """Create sample memories in team space."""
    m1 = Memory.objects.create(
        memory_space=memory_space_team,
        title="Server Config",
        content="Production server runs on port 8080",
        owner_username="bob",
        owner_domain="test.com",
        created_by="bob",
        domain="test.com",
    )
    m2 = Memory.objects.create(
        memory_space=memory_space_team,
        title="API Keys",
        content="API key rotation happens monthly",
        owner_username="alice",
        owner_domain="test.com",
        created_by="alice",
        domain="test.com",
    )
    return [m1, m2]


@pytest.fixture
def personal_memories(memory_space_personal):
    """Create sample memories in personal space for alice."""
    m1 = Memory.objects.create(
        memory_space=memory_space_personal,
        title="My Preferences",
        content="I prefer dark mode",
        owner_username="alice",
        owner_domain="test.com",
        created_by="alice",
        domain="test.com",
    )
    return [m1]


def create_variable_manager(user_id="alice@test.com"):
    """Create a mock variable manager with user context."""
    vm = MagicMock()
    vm.get_variable.side_effect = lambda key, default=None: {
        "flow_input": {"user_id": user_id},
    }.get(key, default)
    return vm


def build_node_config(memory_space_id=None, input_key="last_message", output_key="last_message", top_k=5, title=""):
    """Build node configuration dict."""
    config = {
        "inputParams": input_key,
        "outputParams": output_key,
        "top_k": top_k,
    }
    if memory_space_id:
        config["memorySpace"] = memory_space_id
    if title:
        config["title"] = title
    return {"data": {"config": config}}


# ---------------------------------------------------------------------------
# MemoryRead Node Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMemoryReadPassthrough:
    """MemoryRead node passes through input to output."""

    def test_passthrough_with_memory(self, memory_space_team, team_memories):
        """Output contains original input message."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "Hello world"})

        assert result["last_message"] == "Hello world"

    def test_passthrough_without_memory_space(self):
        """Output contains original input even without memory space configured."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=None)

        result = node.execute("mem_read_1", node_config, {"last_message": "Test input"})

        assert result["last_message"] == "Test input"


@pytest.mark.django_db
class TestMemoryReadPersonalScope:
    """MemoryRead with personal scope respects user permissions."""

    def test_read_personal_memory_as_creator(self, memory_space_personal, personal_memories):
        """Creator can read their own personal memories."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "memory_context" in result
        assert "My Preferences" in result["memory_context"]
        assert "dark mode" in result["memory_context"]

    def test_read_personal_memory_as_non_creator(self, memory_space_personal, personal_memories):
        """Non-creator gets empty memory for personal scope."""
        vm = create_variable_manager("bob@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        # Should passthrough input but no memory_context (or empty)
        assert result["last_message"] == "query"
        assert result.get("memory_context", "") == ""

    def test_read_personal_memory_no_user_id(self, memory_space_personal, personal_memories):
        """No user_id returns empty memory for personal scope."""
        vm = create_variable_manager("")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert result["last_message"] == "query"
        assert result.get("memory_context", "") == ""


@pytest.mark.django_db
class TestMemoryReadTeamScope:
    """MemoryRead with team scope reads all team memories."""

    def test_read_team_memory_returns_all(self, memory_space_team, team_memories):
        """Team scope returns memories from all users."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "memory_context" in result
        # Should contain both memories
        assert "Server Config" in result["memory_context"]
        assert "API Keys" in result["memory_context"]

    def test_read_team_memory_different_user(self, memory_space_team, team_memories):
        """Different user can also read team memories."""
        vm = create_variable_manager("charlie@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "memory_context" in result
        assert "Server Config" in result["memory_context"]


@pytest.mark.django_db
class TestMemoryReadEdgeCases:
    """MemoryRead edge cases."""

    def test_no_memory_space_configured(self):
        """No memory_space_id returns passthrough only."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=None)

        result = node.execute("mem_read_1", node_config, {"last_message": "input"})

        assert result["last_message"] == "input"
        assert "memory_context" not in result or result.get("memory_context") == ""

    def test_memory_space_not_found(self, db):
        """Non-existent memory_space_id returns passthrough only."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=99999)

        result = node.execute("mem_read_1", node_config, {"last_message": "input"})

        assert result["last_message"] == "input"
        assert result.get("memory_context", "") == ""

    def test_empty_memory_space(self, memory_space_team):
        """Empty memory space returns passthrough only."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        result = node.execute("mem_read_1", node_config, {"last_message": "input"})

        assert result["last_message"] == "input"
        # No memories exist, so no memory_context or empty
        assert result.get("memory_context", "") == ""

    def test_top_k_limit(self, memory_space_team):
        """top_k limits the number of memories returned."""
        # Create 5 memories
        for i in range(5):
            Memory.objects.create(
                memory_space=memory_space_team,
                title=f"Memory {i}",
                content=f"Content {i}",
                owner_username="alice",
                owner_domain="test.com",
                created_by="alice",
                domain="test.com",
            )

        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, top_k=2)

        result = node.execute("mem_read_1", node_config, {"last_message": "query"})

        # Should only have 2 memories
        memory_context = result.get("memory_context", "")
        # Count "## Memory" occurrences
        assert memory_context.count("## Memory") == 2

    def test_variable_manager_sets_memory_context(self, memory_space_team, team_memories):
        """memory_context is set in variable_manager for downstream nodes."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        node.execute("mem_read_1", node_config, {"last_message": "query"})

        # Check that set_variable was called with memory_context
        vm.set_variable.assert_called()
        call_args = [call[0] for call in vm.set_variable.call_args_list]
        assert any(args[0] == "memory_context" for args in call_args)


# ---------------------------------------------------------------------------
# MemoryWrite Node Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMemoryWritePassthrough:
    """MemoryWrite node passes through input to output."""

    def test_passthrough_with_write(self, memory_space_team):
        """Output contains original input message."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"last_message": "Important info"})

        assert result["last_message"] == "Important info"

    def test_passthrough_without_memory_space(self):
        """Output contains original input even without memory space configured."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=None)

        result = node.execute("mem_write_1", node_config, {"last_message": "Test input"})

        assert result["last_message"] == "Test input"


@pytest.mark.django_db
class TestMemoryWriteAsyncTask:
    """MemoryWrite triggers async Celery task."""

    def test_triggers_celery_task(self, memory_space_team):
        """process_memory_write.delay is called with correct args for team memory."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="My Title")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content to save"})

            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["memory_space_id"] == memory_space_team.id
            assert call_kwargs["title"] == "My Title"
            assert call_kwargs["content"] == "Content to save"
            # Team memory uses organization_id, owner_username is org name
            assert call_kwargs["organization_id"] == 1
            assert "组织" in call_kwargs["owner_username"] or call_kwargs["owner_username"] == "组织-1"

    def test_auto_generates_title(self, memory_space_team):
        """Title is auto-generated if not provided."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert "自动记忆-mem_write_1" in call_kwargs["title"]


@pytest.mark.django_db
class TestMemoryWriteSkipConditions:
    """MemoryWrite skips write under certain conditions."""

    def test_skip_empty_message(self, memory_space_team):
        """Empty message does not trigger write."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"last_message": ""})

            mock_task.delay.assert_not_called()
            assert result["last_message"] == ""

    def test_skip_no_memory_space(self):
        """No memory_space_id does not trigger write."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=None)

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"last_message": "Content"})

            mock_task.delay.assert_not_called()
            assert result["last_message"] == "Content"

    def test_skip_missing_input_key(self, memory_space_team):
        """Missing input key does not trigger write."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"other_key": "value"})

            mock_task.delay.assert_not_called()
            assert result["last_message"] == ""


@pytest.mark.django_db
class TestMemoryWriteErrorHandling:
    """MemoryWrite handles errors gracefully."""

    def test_task_exception_still_passthrough(self, memory_space_team):
        """Exception in task trigger still returns passthrough."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay.side_effect = Exception("Celery connection failed")
            result = node.execute("mem_write_1", node_config, {"last_message": "Content"})

            # Should still passthrough despite exception
            assert result["last_message"] == "Content"


@pytest.mark.django_db
class TestMemoryWriteUserExtraction:
    """MemoryWrite correctly extracts user/org info based on scope."""

    def test_personal_memory_extracts_username_and_domain(self, memory_space_personal):
        """Personal memory: User ID is split into username and domain."""
        vm = create_variable_manager("bob@company.org")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "bob"
            assert call_kwargs["owner_domain"] == "company.org"
            assert call_kwargs["organization_id"] is None

    def test_personal_memory_handles_username_without_domain(self, memory_space_personal):
        """Personal memory: User ID without @ is treated as username only."""
        vm = create_variable_manager("admin")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "admin"
            assert call_kwargs["owner_domain"] == ""
            assert call_kwargs["organization_id"] is None

    def test_personal_memory_handles_empty_user_id(self, memory_space_personal):
        """Personal memory: Empty user_id defaults to 'system'."""
        vm = create_variable_manager("")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_personal.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "system"
            assert call_kwargs["owner_domain"] == ""
            assert call_kwargs["organization_id"] is None

    def test_team_memory_uses_organization_id(self, memory_space_team):
        """Team memory: Uses organization_id from memory_space.team."""
        vm = create_variable_manager("bob@company.org")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["organization_id"] == 1
            # owner_username is org name (or fallback)
            assert "组织" in call_kwargs["owner_username"] or call_kwargs["owner_username"] == "组织-1"


# ---------------------------------------------------------------------------
# Integration: MemoryRead + MemoryWrite in sequence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMemoryReadWriteIntegration:
    """Integration tests for memory read/write flow."""

    def test_write_then_read_team_memory(self, memory_space_team):
        """Written memory can be read back."""
        # First, directly create a memory (simulating what the Celery task would do)
        Memory.objects.create(
            memory_space=memory_space_team,
            title="Integration Test",
            content="This is integration test content",
            owner_username="alice",
            owner_domain="test.com",
            created_by="alice",
            domain="test.com",
        )

        # Now read it back
        vm = create_variable_manager("alice@test.com")
        read_node = MemoryReadNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        result = read_node.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "Integration Test" in result.get("memory_context", "")
        assert "integration test content" in result.get("memory_context", "")

    def test_personal_memory_isolation(self, memory_space_personal):
        """Personal memories are isolated per user."""
        # Create memories for two different users
        Memory.objects.create(
            memory_space=memory_space_personal,
            title="Alice Secret",
            content="Alice's private data",
            owner_username="alice",
            owner_domain="test.com",
            created_by="alice",
            domain="test.com",
        )
        Memory.objects.create(
            memory_space=memory_space_personal,
            title="Bob Secret",
            content="Bob's private data",
            owner_username="bob",
            owner_domain="test.com",
            created_by="bob",
            domain="test.com",
        )

        # Alice reads - should only see her memory
        vm_alice = create_variable_manager("alice@test.com")
        read_node_alice = MemoryReadNode(vm_alice)
        node_config = build_node_config(memory_space_id=memory_space_personal.id)

        result_alice = read_node_alice.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "Alice Secret" in result_alice.get("memory_context", "")
        assert "Bob Secret" not in result_alice.get("memory_context", "")

        # Bob reads - should only see his memory
        vm_bob = create_variable_manager("bob@test.com")
        read_node_bob = MemoryReadNode(vm_bob)

        result_bob = read_node_bob.execute("mem_read_1", node_config, {"last_message": "query"})

        assert "Bob Secret" in result_bob.get("memory_context", "")
        assert "Alice Secret" not in result_bob.get("memory_context", "")


# ---------------------------------------------------------------------------
# API CRUD Tests (Task 11.1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMemorySpaceViewSetCRUD:
    """Test MemorySpaceViewSet CRUD operations."""

    def test_list_memory_spaces(self, memory_space_team, memory_space_personal):
        """List returns all memory spaces for the team."""
        from types import SimpleNamespace

        from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet

        viewset = MemorySpaceViewSet()
        viewset.kwargs = {}
        viewset.format_kwarg = None

        # Mock request with team filtering
        request = SimpleNamespace(
            user=SimpleNamespace(username="admin", domain="test.com"),
            query_params={},
            COOKIES={"current_team": "1"},
        )
        viewset.request = request

        # Get queryset
        queryset = viewset.get_queryset()
        assert queryset.count() >= 2

    def test_create_memory_space(self, db):
        """Create a new memory space."""
        from apps.opspilot.models.memory_mgmt import MemorySpace

        space = MemorySpace.objects.create(
            name="Test Space",
            introduction="Test intro",
            team=[1],
            scope=MemorySpace.SCOPE_TEAM,
            write_rule="Extract facts",
            default_model="",
            created_by="admin",
            domain="test.com",
        )

        assert space.id is not None
        assert space.name == "Test Space"
        assert space.scope == MemorySpace.SCOPE_TEAM

    def test_retrieve_memory_space(self, memory_space_team):
        """Retrieve a specific memory space."""
        from apps.opspilot.models.memory_mgmt import MemorySpace

        space = MemorySpace.objects.get(id=memory_space_team.id)
        assert space.name == "Team Knowledge Base"
        assert space.scope == MemorySpace.SCOPE_TEAM

    def test_update_memory_space(self, memory_space_team):
        """Update a memory space."""
        memory_space_team.name = "Updated Name"
        memory_space_team.write_rule = "New rule"
        memory_space_team.save()

        memory_space_team.refresh_from_db()
        assert memory_space_team.name == "Updated Name"
        assert memory_space_team.write_rule == "New rule"

    def test_delete_memory_space(self, db):
        """Delete a memory space."""
        from apps.opspilot.models.memory_mgmt import MemorySpace

        space = MemorySpace.objects.create(
            name="To Delete",
            team=[1],
            scope=MemorySpace.SCOPE_TEAM,
            created_by="admin",
            domain="test.com",
        )
        space_id = space.id
        space.delete()

        assert not MemorySpace.objects.filter(id=space_id).exists()

    def test_delete_memory_space_cascades_memories(self, memory_space_team, team_memories):
        """Deleting memory space cascades to memories."""
        from apps.opspilot.models.memory_mgmt import Memory

        memory_ids = [m.id for m in team_memories]
        memory_space_team.delete()

        # All memories should be deleted
        assert Memory.objects.filter(id__in=memory_ids).count() == 0


@pytest.mark.django_db
class TestMemorySpaceTestWriteAction:
    """Test MemorySpaceViewSet test_write action."""

    def test_test_write_empty_input_returns_error(self):
        """Empty input returns 400 error."""
        from types import SimpleNamespace

        from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet

        viewset = MemorySpaceViewSet()
        request = SimpleNamespace(
            data={"input": "", "write_rule": "Extract facts", "model_id": 1},
            user=SimpleNamespace(username="admin"),
        )

        # Call the underlying method directly, bypassing permission decorator
        response = MemorySpaceViewSet.test_write.__wrapped__(viewset, request)
        assert response.status_code == 400

    def test_test_write_no_write_rule_returns_input(self):
        """No write_rule returns input as-is."""
        from types import SimpleNamespace

        from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet

        viewset = MemorySpaceViewSet()
        request = SimpleNamespace(
            data={"input": "Test content", "write_rule": "", "model_id": None},
            user=SimpleNamespace(username="admin"),
        )

        response = MemorySpaceViewSet.test_write.__wrapped__(viewset, request)
        assert response.status_code == 200
        import json

        data = json.loads(response.content)
        assert data["data"]["result"] == "Test content"

    def test_test_write_no_model_id_returns_error(self):
        """No model_id with write_rule returns 400 error."""
        from types import SimpleNamespace

        from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet

        viewset = MemorySpaceViewSet()
        request = SimpleNamespace(
            data={"input": "Test content", "write_rule": "Extract facts", "model_id": None},
            user=SimpleNamespace(username="admin"),
        )

        response = MemorySpaceViewSet.test_write.__wrapped__(viewset, request)
        assert response.status_code == 400

    def test_test_write_model_not_found_returns_404(self, db):
        """Non-existent model_id returns 404."""
        from types import SimpleNamespace

        from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet

        viewset = MemorySpaceViewSet()
        request = SimpleNamespace(
            data={"input": "Test content", "write_rule": "Extract facts", "model_id": 99999},
            user=SimpleNamespace(username="admin"),
        )

        response = MemorySpaceViewSet.test_write.__wrapped__(viewset, request)
        assert response.status_code == 404


@pytest.mark.django_db
class TestMemoryViewSetCRUD:
    """Test MemoryViewSet CRUD operations."""

    def test_create_memory(self, memory_space_team):
        """Create a new memory."""
        memory = Memory.objects.create(
            memory_space=memory_space_team,
            title="New Memory",
            content="New content",
            owner_username="alice",
            owner_domain="test.com",
            created_by="alice",
            domain="test.com",
        )

        assert memory.id is not None
        assert memory.title == "New Memory"

    def test_retrieve_memory(self, memory_space_team, team_memories):
        """Retrieve a specific memory."""
        memory = Memory.objects.get(id=team_memories[0].id)
        assert memory.title == "Server Config"

    def test_update_memory(self, memory_space_team, team_memories):
        """Update a memory."""
        memory = team_memories[0]
        memory.title = "Updated Title"
        memory.content = "Updated content"
        memory.save()

        memory.refresh_from_db()
        assert memory.title == "Updated Title"
        assert memory.content == "Updated content"

    def test_delete_memory(self, memory_space_team, team_memories):
        """Delete a memory."""
        memory_id = team_memories[0].id
        team_memories[0].delete()

        assert not Memory.objects.filter(id=memory_id).exists()

    def test_list_team_memories_returns_all(self, memory_space_team, team_memories):
        """Team scope memories are visible to all team members."""
        memories = Memory.objects.filter(memory_space=memory_space_team)
        assert memories.count() == 2

    def test_list_personal_memories_filtered_by_owner(self, memory_space_personal, personal_memories):
        """Personal scope memories are filtered by owner."""
        # Create another user's memory in the same personal space
        Memory.objects.create(
            memory_space=memory_space_personal,
            title="Bob's Note",
            content="Bob's content",
            owner_username="bob",
            owner_domain="test.com",
            created_by="bob",
            domain="test.com",
        )

        # Alice should only see her own memories
        alice_memories = Memory.objects.filter(
            memory_space=memory_space_personal,
            owner_username="alice",
            owner_domain="test.com",
        )
        assert alice_memories.count() == 1
        assert alice_memories.first().title == "My Preferences"

        # Bob should only see his own memories
        bob_memories = Memory.objects.filter(
            memory_space=memory_space_personal,
            owner_username="bob",
            owner_domain="test.com",
        )
        assert bob_memories.count() == 1
        assert bob_memories.first().title == "Bob's Note"


# ---------------------------------------------------------------------------
# LLM Memory Extraction and Merge Tests (Task 11.5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProcessMemoryWriteNoModel:
    """Test process_memory_write when no model is configured."""

    def test_no_default_model_creates_memory_directly(self, memory_space_team):
        """Without default_model, memory is created directly without LLM."""
        from apps.opspilot.tasks import process_memory_write

        # Ensure no default_model
        memory_space_team.default_model = ""
        memory_space_team.save()

        with patch("apps.opspilot.tasks.close_old_connections"):
            process_memory_write(
                memory_space_id=memory_space_team.id,
                title="Direct Memory",
                content="Content without LLM processing",
                owner_username="alice",
                owner_domain="test.com",
            )

        memory = Memory.objects.filter(memory_space=memory_space_team, title="Direct Memory").first()
        assert memory is not None
        assert memory.content == "Content without LLM processing"

    def test_model_not_found_creates_memory_directly(self, memory_space_team):
        """Non-existent model_id creates memory directly."""
        from apps.opspilot.tasks import process_memory_write

        memory_space_team.default_model = "99999"
        memory_space_team.save()

        with patch("apps.opspilot.tasks.close_old_connections"):
            process_memory_write(
                memory_space_id=memory_space_team.id,
                title="Fallback Memory",
                content="Content with missing model",
                owner_username="alice",
                owner_domain="test.com",
            )

        memory = Memory.objects.filter(memory_space=memory_space_team, title="Fallback Memory").first()
        assert memory is not None


@pytest.mark.django_db
class TestProcessMemoryWriteNoExistingMemories:
    """Test process_memory_write when no existing memories."""

    def test_no_existing_memories_creates_new(self, db):
        """With no existing memories, creates new memory directly."""
        from apps.opspilot.tasks import process_memory_write

        # Create memory space with model
        space = MemorySpace.objects.create(
            name="Empty Space",
            team=[1],
            scope=MemorySpace.SCOPE_TEAM,
            write_rule="",
            default_model="",
            created_by="admin",
            domain="test.com",
        )

        with patch("apps.opspilot.tasks.close_old_connections"):
            process_memory_write(
                memory_space_id=space.id,
                title="First Memory",
                content="First content",
                owner_username="alice",
                owner_domain="test.com",
            )

        memory = Memory.objects.filter(memory_space=space).first()
        assert memory is not None
        assert memory.title == "First Memory"


def create_test_llm_model(db):
    """Helper to create a test LLMModel with vendor."""
    from apps.opspilot.models import LLMModel
    from apps.opspilot.models.model_provider_mgmt import ModelVendor

    vendor = ModelVendor.objects.create(
        name="Test Vendor",
        vendor_type="openai",
        protocol_type="openai",
        api_base="http://test",
        api_key="test-key",
        team=[1],
    )
    llm_model = LLMModel.objects.create(
        name="Test Model",
        model="gpt-4",
        vendor=vendor,
        team=[1],
    )
    return llm_model


@pytest.mark.django_db
class TestProcessMemoryWriteWithLLM:
    """Test process_memory_write with LLM decision making."""

    def test_llm_decides_create_new_memory(self, memory_space_team, team_memories):
        """LLM decides to create new memory for unrelated content."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.save()

        # Mock LLM response for "create" decision
        mock_response = MagicMock()
        mock_response.content = '```json\n{"action": "create", "memory_id": null, "title": "New Topic", "content": "Completely new content"}\n```'

        mock_client = MagicMock()
        mock_client.invoke.return_value = mock_response

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="New Topic",
                    content="Completely new content",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # Should have created a new memory
        new_memory = Memory.objects.filter(memory_space=memory_space_team, title="New Topic").first()
        assert new_memory is not None
        assert new_memory.content == "Completely new content"

    def test_llm_decides_update_existing_memory(self, memory_space_team, team_memories):
        """LLM decides to update existing memory for related content."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.save()

        existing_memory = team_memories[0]

        # Mock LLM response for "update" decision with merged content
        mock_response = MagicMock()
        mock_response.content = (
            f'{{"action": "update", "memory_id": {existing_memory.id}, '
            f'"title": "Server Config", '
            f'"content": "Production server runs on port 8080\\nAlso supports port 443 for HTTPS"}}'
        )

        mock_client = MagicMock()
        mock_client.invoke.return_value = mock_response

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="Server Config Update",
                    content="Also supports port 443 for HTTPS",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # Should have updated the existing memory
        existing_memory.refresh_from_db()
        assert "port 8080" in existing_memory.content
        assert "port 443" in existing_memory.content

    def test_llm_json_parse_error_creates_new_memory(self, memory_space_team, team_memories):
        """JSON parse error falls back to creating new memory."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.save()

        # Mock LLM response with invalid JSON
        mock_response = MagicMock()
        mock_response.content = "This is not valid JSON at all"

        mock_client = MagicMock()
        mock_client.invoke.return_value = mock_response

        initial_count = Memory.objects.filter(memory_space=memory_space_team).count()

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="Fallback Title",
                    content="Fallback content",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # Should have created a new memory as fallback
        assert Memory.objects.filter(memory_space=memory_space_team).count() == initial_count + 1


@pytest.mark.django_db
class TestProcessMemoryWriteWriteRule:
    """Test process_memory_write with write_rule normalization."""

    def test_write_rule_normalizes_content(self, memory_space_team):
        """write_rule is used to normalize content before decision."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.write_rule = "Extract key facts as bullet points"
        memory_space_team.save()

        # First call normalizes content, second call makes decision
        call_count = [0]

        def mock_invoke(messages):
            call_count[0] += 1
            mock_resp = MagicMock()
            if call_count[0] == 1:
                # First call: write_rule normalization
                mock_resp.content = "- Key fact 1\n- Key fact 2"
            else:
                # Second call: decision
                mock_resp.content = '{"action": "create", "memory_id": null, "title": "Facts", "content": "- Key fact 1\\n- Key fact 2"}'
            return mock_resp

        mock_client = MagicMock()
        mock_client.invoke.side_effect = mock_invoke

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="Raw Input",
                    content="Some raw content to normalize",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # write_rule should have been invoked
        assert call_count[0] >= 1

    def test_write_rule_error_uses_original_content(self, memory_space_team):
        """write_rule error falls back to original content."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.write_rule = "Extract facts"
        memory_space_team.save()

        call_count = [0]

        def mock_invoke(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: write_rule fails
                raise Exception("LLM error")
            mock_resp = MagicMock()
            mock_resp.content = '{"action": "create", "memory_id": null, "title": "Test", "content": "Original content"}'
            return mock_resp

        mock_client = MagicMock()
        mock_client.invoke.side_effect = mock_invoke

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="Test",
                    content="Original content",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # Should still create memory with original content
        memory = Memory.objects.filter(memory_space=memory_space_team, title="Test").first()
        assert memory is not None


@pytest.mark.django_db
class TestProcessMemoryWriteUpdateTargetNotFound:
    """Test process_memory_write when update target doesn't exist."""

    def test_update_target_not_found_creates_new(self, memory_space_team, team_memories):
        """If LLM specifies non-existent memory_id, creates new memory."""
        from apps.opspilot.tasks import process_memory_write

        llm_model = create_test_llm_model(None)
        memory_space_team.default_model = str(llm_model.id)
        memory_space_team.save()

        # Mock LLM response with non-existent memory_id
        mock_response = MagicMock()
        mock_response.content = '{"action": "update", "memory_id": 99999, "title": "Ghost Memory", "content": "Content for ghost"}'

        mock_client = MagicMock()
        mock_client.invoke.return_value = mock_response

        initial_count = Memory.objects.filter(memory_space=memory_space_team).count()

        with patch("apps.opspilot.tasks.close_old_connections"):
            with patch("apps.opspilot.metis.llm.common.llm_client_factory.LLMClientFactory.create_client", return_value=mock_client):
                process_memory_write(
                    memory_space_id=memory_space_team.id,
                    title="Ghost Memory",
                    content="Content for ghost",
                    owner_username="alice",
                    owner_domain="test.com",
                )

        # Should have created a new memory since target doesn't exist
        assert Memory.objects.filter(memory_space=memory_space_team).count() == initial_count + 1
        new_memory = Memory.objects.filter(memory_space=memory_space_team, title="Ghost Memory").first()
        assert new_memory is not None


# ---------------------------------------------------------------------------
# Workflow Integration Tests: Entry → MemoryRead → Agent → MemoryWrite
# ---------------------------------------------------------------------------


def build_memory_workflow_flow(memory_space_id: int):
    """Build a 4-node workflow: entry → memory_read → agent → memory_write."""
    return {
        "nodes": [
            {
                "id": "entry_node",
                "type": "openai",
                "data": {"label": "Entry", "config": {}},
            },
            {
                "id": "memory_read_node",
                "type": "memory_read",
                "data": {
                    "label": "Read Memory",
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "last_message",
                        "memorySpace": memory_space_id,
                        "top_k": 5,
                    },
                },
            },
            {
                "id": "agent_node",
                "type": "agents",
                "data": {
                    "label": "Agent",
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "last_message",
                        # Prompt uses memory_context from MemoryRead
                        "prompt": "You have access to these memories:\n{{ memory_context }}\n\nUser question: {{ last_message }}",
                    },
                },
            },
            {
                "id": "memory_write_node",
                "type": "memory_write",
                "data": {
                    "label": "Write Memory",
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "last_message",
                        "memorySpace": memory_space_id,
                        "title": "Conversation Memory",
                    },
                },
            },
        ],
        "edges": [
            {"id": "edge_1", "source": "entry_node", "target": "memory_read_node"},
            {"id": "edge_2", "source": "memory_read_node", "target": "agent_node"},
            {"id": "edge_3", "source": "agent_node", "target": "memory_write_node"},
        ],
    }


class FakeAgentExecutorWithMemory:
    """Fake agent executor that echoes input and memory_context."""

    def __init__(self, variable_manager):
        self.variable_manager = variable_manager

    def execute(self, node_id, node_config, input_data):
        input_key = node_config.get("data", {}).get("config", {}).get("inputParams", "last_message")
        output_key = node_config.get("data", {}).get("config", {}).get("outputParams", "last_message")
        received = input_data.get(input_key, "")

        # Get memory_context from variable_manager (set by MemoryRead)
        memory_context = self.variable_manager.get_variable("memory_context", "")

        # Echo back with memory info
        response = f"Agent received: {received}"
        if memory_context:
            response += f" | Memory: {memory_context[:50]}..."

        return {output_key: response}


@pytest.mark.django_db(transaction=True)
class TestMemoryWorkflowIntegration:
    """Integration tests for memory workflow: entry → memory_read → agent → memory_write."""

    @pytest.fixture
    def memory_workflow(self, db, mocker):
        """Create a BotWorkFlow with memory nodes."""
        from apps.opspilot.models.bot_mgmt import Bot, BotWorkFlow

        mocker.patch(
            "apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow",
            return_value=(0, 0, 0),
        )

        # Create memory space
        space = MemorySpace.objects.create(
            name="Workflow Test Space",
            team=[1],
            scope=MemorySpace.SCOPE_TEAM,
            write_rule="",
            default_model="",
            created_by="admin",
            domain="test.com",
        )

        # Create some memories
        Memory.objects.create(
            memory_space=space,
            title="User Preference",
            content="User prefers dark mode and Python",
            owner_username="alice",
            owner_domain="test.com",
            created_by="alice",
            domain="test.com",
        )

        bot = Bot.objects.create(
            name="memory-test-bot",
            team=[1],
            online=True,
            created_by="tester",
            domain="test.com",
        )

        workflow = BotWorkFlow.objects.create(
            bot=bot,
            flow_json=build_memory_workflow_flow(space.id),
        )

        return {"workflow": workflow, "space": space, "bot": bot}

    def test_memory_read_passes_context_to_agent(self, memory_workflow):
        """MemoryRead sets memory_context that agent can access."""
        from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

        workflow = memory_workflow["workflow"]
        engine = create_chat_flow_engine(workflow, "entry_node")

        # Inject fake agent executor
        engine.custom_node_executors["agents"] = FakeAgentExecutorWithMemory(engine.variable_manager)

        # Mock memory_write task to avoid Celery
        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()

            result = engine.execute(
                {
                    "last_message": "What are my preferences?",
                    "user_id": "alice@test.com",
                }
            )

        # Agent should have received memory_context
        assert "Memory:" in result or "User Preference" in str(result)

    def test_memory_write_triggered_after_agent(self, memory_workflow):
        """MemoryWrite triggers async task after agent completes."""
        from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

        workflow = memory_workflow["workflow"]
        space = memory_workflow["space"]
        engine = create_chat_flow_engine(workflow, "entry_node")

        engine.custom_node_executors["agents"] = FakeAgentExecutorWithMemory(engine.variable_manager)

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()

            engine.execute(
                {
                    "last_message": "Remember that I like coffee",
                    "user_id": "alice@test.com",
                }
            )

            # MemoryWrite should have triggered the Celery task
            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["memory_space_id"] == space.id
            assert call_kwargs["owner_username"] == "alice"

    def test_full_workflow_executes_all_nodes(self, memory_workflow):
        """All 4 nodes execute in correct order."""
        from apps.opspilot.models.bot_mgmt import WorkFlowTaskNodeResult
        from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

        workflow = memory_workflow["workflow"]
        engine = create_chat_flow_engine(workflow, "entry_node")

        engine.custom_node_executors["agents"] = FakeAgentExecutorWithMemory(engine.variable_manager)

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()

            engine.execute(
                {
                    "last_message": "Hello",
                    "user_id": "alice@test.com",
                }
            )

        # Check all nodes executed
        node_results = WorkFlowTaskNodeResult.objects.filter(
            execution_id=engine.execution_id,
        ).order_by("node_index")

        assert node_results.count() == 4

        node_ids = [r.node_id for r in node_results]
        assert "entry_node" in node_ids
        assert "memory_read_node" in node_ids
        assert "agent_node" in node_ids
        assert "memory_write_node" in node_ids

    def test_personal_memory_isolation_in_workflow(self, db, mocker):
        """Personal memory space only returns current user's memories."""
        from apps.opspilot.models.bot_mgmt import Bot, BotWorkFlow
        from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

        mocker.patch(
            "apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow",
            return_value=(0, 0, 0),
        )

        # Create personal memory space
        space = MemorySpace.objects.create(
            name="Personal Space",
            team=[1],
            scope=MemorySpace.SCOPE_PERSONAL,
            created_by="admin",
            domain="test.com",
        )

        # Create memories for different users
        Memory.objects.create(
            memory_space=space,
            title="Alice Secret",
            content="Alice's private data",
            owner_username="alice",
            owner_domain="test.com",
            created_by="alice",
            domain="test.com",
        )
        Memory.objects.create(
            memory_space=space,
            title="Bob Secret",
            content="Bob's private data",
            owner_username="bob",
            owner_domain="test.com",
            created_by="bob",
            domain="test.com",
        )

        bot = Bot.objects.create(
            name="personal-test-bot",
            team=[1],
            online=True,
            created_by="tester",
            domain="test.com",
        )

        workflow = BotWorkFlow.objects.create(
            bot=bot,
            flow_json=build_memory_workflow_flow(space.id),
        )

        engine = create_chat_flow_engine(workflow, "entry_node")
        engine.custom_node_executors["agents"] = FakeAgentExecutorWithMemory(engine.variable_manager)

        with patch("apps.opspilot.memory.engines.local_engine.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()

            # Execute as Alice
            engine.execute(
                {
                    "last_message": "Show my secrets",
                    "user_id": "alice@test.com",
                }
            )

        # Check memory_context only contains Alice's data
        memory_context = engine.variable_manager.get_variable("memory_context", "")
        assert "Alice Secret" in memory_context
        assert "Bob Secret" not in memory_context
