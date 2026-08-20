import logging
import sys

from discovery import config
from discovery.adapters.career_page import CareerPageAdapter
from discovery.adapters.github_list import (
    RELEVANT_CATEGORIES,
    SIMPLIFYJOBS_REPO,
    VANSHB03_REPO,
    GitHubListAdapter,
)
from discovery.adapters.job_board import JobBoardAdapter
from discovery.adapters.web_search import WebSearchAdapter
from discovery.gemini_client import GeminiClient
from discovery.pipeline import run_discovery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("discover")


def build_adapters(gemini_client: GeminiClient):
    company_boards = config.load_company_boards()
    career_pages = config.load_career_pages()
    search_queries = config.load_search_queries()
    google_api_key, google_cx = config.get_google_search_config()

    return [
        GitHubListAdapter(
            repo=SIMPLIFYJOBS_REPO,
            source_name="simplifyjobs_github",
            category_filter=RELEVANT_CATEGORIES,
        ),
        GitHubListAdapter(
            repo=VANSHB03_REPO,
            source_name="vanshb03_github",
            category_filter=None,
        ),
        JobBoardAdapter(companies=company_boards),
        WebSearchAdapter(
            queries=search_queries,
            google_api_key=google_api_key,
            google_cx=google_cx,
            gemini_client=gemini_client,
        ),
        CareerPageAdapter(pages=career_pages, gemini_client=gemini_client),
    ]


def main() -> int:
    try:
        gemini_client = GeminiClient()
        adapters = build_adapters(gemini_client)
    except RuntimeError as exc:
        logger.error("Discovery run aborted: %s", exc)
        return 1

    summary = run_discovery(adapters=adapters, classifier_client=gemini_client)

    logger.info(
        "Discovery run complete: found=%d passed_filter=%d written=%d errors=%d",
        summary.found,
        summary.passed_filter,
        summary.written,
        len(summary.errors),
    )
    for error in summary.errors:
        logger.warning("Adapter error: %s", error)

    return 0


if __name__ == "__main__":
    sys.exit(main())
