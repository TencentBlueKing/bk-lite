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

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
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
        """process_memory_write.delay is called with correct args."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="My Title")

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content to save"})

            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["memory_space_id"] == memory_space_team.id
            assert call_kwargs["title"] == "My Title"
            assert call_kwargs["content"] == "Content to save"
            assert call_kwargs["owner_username"] == "alice"
            assert call_kwargs["owner_domain"] == "test.com"

    def test_auto_generates_title(self, memory_space_team):
        """Title is auto-generated if not provided."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="")

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
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

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"last_message": ""})

            mock_task.delay.assert_not_called()
            assert result["last_message"] == ""

    def test_skip_no_memory_space(self):
        """No memory_space_id does not trigger write."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=None)

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            result = node.execute("mem_write_1", node_config, {"last_message": "Content"})

            mock_task.delay.assert_not_called()
            assert result["last_message"] == "Content"

    def test_skip_missing_input_key(self, memory_space_team):
        """Missing input key does not trigger write."""
        vm = create_variable_manager("alice@test.com")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id)

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
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

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay.side_effect = Exception("Celery connection failed")
            result = node.execute("mem_write_1", node_config, {"last_message": "Content"})

            # Should still passthrough despite exception
            assert result["last_message"] == "Content"


@pytest.mark.django_db
class TestMemoryWriteUserExtraction:
    """MemoryWrite correctly extracts user info."""

    def test_extracts_username_and_domain(self, memory_space_team):
        """User ID is split into username and domain."""
        vm = create_variable_manager("bob@company.org")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "bob"
            assert call_kwargs["owner_domain"] == "company.org"

    def test_handles_username_without_domain(self, memory_space_team):
        """User ID without @ is treated as username only."""
        vm = create_variable_manager("admin")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "admin"
            assert call_kwargs["owner_domain"] == ""

    def test_handles_empty_user_id(self, memory_space_team):
        """Empty user_id defaults to 'system'."""
        vm = create_variable_manager("")
        node = MemoryWriteNode(vm)
        node_config = build_node_config(memory_space_id=memory_space_team.id, title="Test")

        with patch("apps.opspilot.tasks.process_memory_write") as mock_task:
            mock_task.delay = MagicMock()
            node.execute("mem_write_1", node_config, {"last_message": "Content"})

            call_kwargs = mock_task.delay.call_args[1]
            assert call_kwargs["owner_username"] == "system"
            assert call_kwargs["owner_domain"] == ""


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
