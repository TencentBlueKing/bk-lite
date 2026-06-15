"""K8s report-tool gating (F058).

Two report-rendering tools are K8s-specific:

- ``report_config_diff``     (built by ``ToolsNodes._build_diff_report_tool``)
- ``generate_repair_report`` (built by ``ToolsNodes._build_bulk_repair_tool``)

Historically these were bound to *every* agent that had any tools at all, even
agents whose tool pool has nothing to do with Kubernetes. The frontend only
renders the ``config_diff_report`` / repair-report events when present, so an
agent that never deals with K8s carrying these tools is pure overhead (extra
tool schema in every LLM call, extra surface for the model to misfire on).

This module isolates the *decision* of whether an agent is "K8s-flavoured" so
that ``build_react_nodes`` can gate the two report tools behind it. The
decision is intentionally based on the agent's actual tool pool rather than on
the request's ``tools_servers`` list, because:

* the production K8s tool servers (``langchain:kubernetes`` /
  ``langchain:kubernetes_data_collection``) load tools whose names contain
  ``kubernetes`` and/or the config-analysis trigger
  ``analyze_deployment_configurations``; and
* the existing react-agent tests drive ``build_react_nodes`` directly with
  ``node_builder.tools = [analyze_deployment_configurations]`` and never call
  ``setup()``/populate ``tools_servers``.

Keying off tool *names* keeps both paths working.
"""

from typing import Any, Iterable

# Tools that unambiguously mark an agent as operating on Kubernetes. The
# config-analysis entry tool is the one that feeds the repair-report cache, so
# its presence is the strongest signal that the two report tools are useful.
_K8S_MARKER_TOOL_NAMES = frozenset(
    {
        "analyze_deployment_configurations",
    }
)

# Any tool whose (lower-cased) name contains one of these substrings also marks
# the agent as K8s-flavoured.
_K8S_NAME_SUBSTRINGS = (
    "kubernetes",
    "kubectl",
)


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", "") or "")


def is_k8s_agent(tools: Iterable[Any]) -> bool:
    """Return True if the given tool pool indicates a Kubernetes agent.

    Args:
        tools: iterable of tool objects (StructuredTool / BaseTool-like). Each
            is inspected by its ``.name`` attribute only; missing names are
            ignored.
    """
    for tool in tools or []:
        name = _tool_name(tool)
        if not name:
            continue
        if name in _K8S_MARKER_TOOL_NAMES:
            return True
        lowered = name.lower()
        if any(sub in lowered for sub in _K8S_NAME_SUBSTRINGS):
            return True
    return False
