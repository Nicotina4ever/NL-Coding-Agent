import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _reset_ui_language():
    try:
        from nl_coding_agent.gui.i18n import reset_i18n
        reset_i18n()
    except Exception:
        pass
    yield
    try:
        from nl_coding_agent.gui.i18n import reset_i18n
        reset_i18n()
    except Exception:
        pass
