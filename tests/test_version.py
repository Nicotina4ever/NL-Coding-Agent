import sys
sys.path.append('..')
from nl_coding_agent.core.version import APP_VERSION

def test_version():
    assert APP_VERSION == '0.2.0'
