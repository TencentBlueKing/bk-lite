"""
Workflow E2E test fixtures.

Provides reusable fixtures for creating Bot, BotWorkFlow and
injecting fake node executors so the full ChatFlowEngine path
runs without hitting real LLM / external services.
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub out optional C-extension modules that may not be installed in the
# test environment.  This mirrors the pattern used by existing opspilot tests.
# ---------------------------------------------------------------------------
for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from apps.opspilot.models.bot_mgmt import Bot, BotWorkFlow  # noqa: E402

FIXTURE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Minimal flow_json builders
# ---------------------------------------------------------------------------


def build_two_node_flow(entry_type="openai"):
    """Return a minimal two-node flow_json: entry -> agents."""
    return {
        "nodes": [
            {
                "id": "entry_node",
                "type": entry_type,
                "data": {"label": "Entry", "config": {}},
            },
            {
                "id": "agent_node",
                "type": "agents",
                "data": {
                    "label": "Test Agent",
                    "config": {
                        "inputParams": "last_message",
                        "outputParams": "last_message",
                    },
                },
            },
        ],
        "edges": [
            {"id": "edge_1", "source": "entry_node", "target": "agent_node"},
        ],
    }


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bot(db):
    """Create a minimal online Bot for testing."""
    return Bot.objects.create(
        name="test-bot",
        team=[1],
        online=True,
        created_by="tester",
        domain="test.com",
    )


@pytest.fixture
def bot_workflow(bot, mocker):
    """Create a BotWorkFlow with a two-node flow.

    Mocks ChatApplication.sync_applications_from_workflow to avoid
    side-effects during save().
    """
    mocker.patch(
        "apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow",
        return_value=(0, 0, 0),
    )
    return BotWorkFlow.objects.create(
        bot=bot,
        flow_json=build_two_node_flow(),
    )


@pytest.fixture
def intent_workflow(bot, mocker):
    """Create a BotWorkFlow using the exported flow_json from production id=4.

    The flow has 5 entry nodes, 1 intent classifier, and 10 intent->agent branches.
    """
    mocker.patch(
        "apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow",
        return_value=(0, 0, 0),
    )
    data = json.loads((FIXTURE_DIR / "scenarios" / "flow_json_id4.json").read_text(encoding="utf-16"))
    return BotWorkFlow.objects.create(
        bot=bot,
        flow_json=data["flow_json"],
    )
