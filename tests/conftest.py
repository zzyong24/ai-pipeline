import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_llm_research():
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.return_value = '[{"title":"测试视频","url":"https://www.bilibili.com/video/BV_test/","platform":"bilibili","note":"测试"}]'
        yield m


@pytest.fixture
def mock_llm_summarize():
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.return_value = "这是一段测试摘要内容，用于验证流程正常工作。"
        yield m


@pytest.fixture
def mock_llm_error():
    with patch("subgraphs.shared.llm.llm_minimax") as m:
        m.side_effect = RuntimeError("MINIMAX_CN_API_KEY 未设置")
        yield m
