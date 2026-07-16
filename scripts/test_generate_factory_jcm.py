import pytest
import re
from generate_factory_jcm import rewrite_content, CANONICAL_TOKENS

def test_rewrite_content_basic():
    content = "agent supervisor : supervisor_agent.asl {\n"
    res = rewrite_content(content, 42)
    assert "supervisor_42" in res

def test_rewrite_content_boundary():
    content = "focus: factory_ws.station_1"
    res = rewrite_content(content, 42)
    assert "station_1_42" in res

def test_rewrite_content_no_partial_match():
    content = "focus: factory_ws.supervisor_artifact"
    res = rewrite_content(content, 42)
    assert "supervisor_42_artifact" not in res
    assert "supervisor_artifact" in res

def test_all_tokens():
    for token in CANONICAL_TOKENS:
        content = f" {token} "
        res = rewrite_content(content, 99)
        assert f" {token}_99 " in res
