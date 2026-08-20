import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

COMPANIES_FILE = Path(__file__).parent / "companies.yaml"


@dataclass
class CompanyBoardConfig:
    name: str
    board_type: str
    board_slug: str


@dataclass
class CareerPageConfig:
    name: str
    url: str


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_company_boards(path: Path = COMPANIES_FILE) -> list[CompanyBoardConfig]:
    raw = _load_yaml(path)
    return [
        CompanyBoardConfig(
            name=c["name"], board_type=c["board_type"], board_slug=c["board_slug"]
        )
        for c in raw.get("companies", [])
    ]


def load_career_pages(path: Path = COMPANIES_FILE) -> list[CareerPageConfig]:
    raw = _load_yaml(path)
    return [
        CareerPageConfig(name=c["name"], url=c["url"])
        for c in raw.get("career_pages", [])
    ]


def load_search_queries(path: Path = COMPANIES_FILE) -> list[str]:
    raw = _load_yaml(path)
    return list(raw.get("search_queries", []))


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set in environment")
    return key


def get_gemini_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def get_google_search_config() -> tuple[str, str]:
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_CX")
    if not api_key or not cx:
        raise RuntimeError("GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX not set")
    return api_key, cx
