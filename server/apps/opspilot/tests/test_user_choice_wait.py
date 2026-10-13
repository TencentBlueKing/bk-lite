"""阻塞等待已删除。续接行为见 test_pending_question.py。"""

import pytest


def test_blocking_choice_api_removed():
    import apps.opspilot.utils.user_choice as user_choice

    assert not hasattr(user_choice, "wait_for_choice")
    assert not hasattr(user_choice, "submit_user_choice")
    with pytest.raises(ModuleNotFoundError):
        __import__("apps.opspilot.utils.pending_hitl")
