import textwrap
import pytest
from discovery import config


SAMPLE_YAML = textwrap.dedent("""
    companies:
      - name: "Acme"
        board_type: greenhouse
        board_slug: acme
      - name: "Widgets Inc"
        board_type: lever
        board_slug: widgets

    career_pages:
      - name: "BigCo"
        url: "https://bigco.example.com/careers"

    search_queries:
      - "software engineer intern Summer 2027"
    """)


@pytest.fixture()
def sample_config_file(tmp_path):
    path = tmp_path / "companies.yaml"
    path.write_text(SAMPLE_YAML)
    return path


def test_load_company_boards(sample_config_file):
    boards = config.load_company_boards(sample_config_file)
    assert boards == [
        config.CompanyBoardConfig(name="Acme", board_type="greenhouse", board_slug="acme"),
        config.CompanyBoardConfig(name="Widgets Inc", board_type="lever", board_slug="widgets"),
    ]


def test_load_career_pages(sample_config_file):
    pages = config.load_career_pages(sample_config_file)
    assert pages == [
        config.CareerPageConfig(name="BigCo", url="https://bigco.example.com/careers"),
    ]


def test_load_search_queries(sample_config_file):
    queries = config.load_search_queries(sample_config_file)
    assert queries == ["software engineer intern Summer 2027"]


def test_get_gemini_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.get_gemini_api_key()


def test_get_gemini_api_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert config.get_gemini_api_key() == "test-key-123"


def test_get_gemini_model_name_defaults(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert config.get_gemini_model_name() == "gemini-3.6-flash"


def test_get_gemini_model_name_override(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    assert config.get_gemini_model_name() == "gemini-custom"


def test_get_google_search_config(monkeypatch):
    monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "search-key")
    monkeypatch.setenv("GOOGLE_SEARCH_CX", "cx-123")
    assert config.get_google_search_config() == ("search-key", "cx-123")


def test_get_google_search_config_missing_raises(monkeypatch):
    monkeypatch.delenv("GOOGLE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_CX", raising=False)
    with pytest.raises(RuntimeError):
        config.get_google_search_config()
