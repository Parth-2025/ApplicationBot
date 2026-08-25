import json
import threading
import time

import google.generativeai as genai

from . import config


class GeminiError(Exception):
    pass


class GeminiQuotaExhaustedError(GeminiError):
    """Raised when Gemini's daily free-tier quota is exhausted. Retrying
    within the same run is pointless - the quota resets on Google's clock,
    not ours - so callers should stop issuing new calls rather than retry."""


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        model=None,
        request_timeout: float = 30.0,
        min_seconds_between_calls: float = 13.0,
    ):
        self._request_timeout = request_timeout
        # The free tier caps requests per minute (observed: 5 RPM on
        # gemini-3.6-flash). 13s between calls keeps every caller sharing
        # this client - classification, career-page extraction, web-search
        # extraction - under that ceiling without each needing its own
        # pacing logic. The lock serializes pacing itself, not the calls:
        # concurrent callers still each get their own turn, just spaced out.
        self._min_seconds_between_calls = min_seconds_between_calls
        self._pacing_lock = threading.Lock()
        self._last_call_started_at: float | None = None
        if model is not None:
            self._model = model
            return
        genai.configure(api_key=api_key or config.get_gemini_api_key())
        self._model = genai.GenerativeModel(model_name or config.get_gemini_model_name())

    def _wait_for_rate_limit(self) -> None:
        with self._pacing_lock:
            now = time.monotonic()
            if self._last_call_started_at is not None:
                wait = self._min_seconds_between_calls - (now - self._last_call_started_at)
                if wait > 0:
                    time.sleep(wait)
                    now = time.monotonic()
            self._last_call_started_at = now

    def _call_model(self, prompt: str):
        # The google-generativeai SDK's own request_options timeout isn't
        # reliably honored on every transport path (observed hanging past
        # its stated timeout during a live run). A daemon thread with a
        # hard join() deadline guarantees this call returns or raises
        # regardless of what the SDK does internally - and being a daemon
        # thread, an SDK call that never returns won't block process exit.
        result: dict = {}

        def target():
            try:
                result["response"] = self._model.generate_content(
                    prompt, request_options={"timeout": self._request_timeout}
                )
            except Exception as exc:  # noqa: BLE001 - captured and re-raised on the caller's thread
                result["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=self._request_timeout)

        if thread.is_alive():
            raise TimeoutError(
                f"Gemini call did not return within {self._request_timeout}s"
            )
        if "error" in result:
            raise result["error"]
        return result["response"]

    def _generate_with_retry(self, prompt: str, retries: int) -> str:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self._call_model(prompt)
                return response.text.strip()
            except Exception as exc:  # noqa: BLE001 - any Gemini SDK/network failure
                last_error = exc
                # Daily-quota exhaustion won't clear up by retrying seconds
                # later like a per-minute rate limit would - stop immediately
                # rather than burn the retry budget on a guaranteed failure.
                if "PerDay" in str(exc):
                    raise GeminiQuotaExhaustedError(
                        f"Gemini daily quota exhausted: {exc}"
                    ) from exc
                if attempt < retries:
                    time.sleep(2**attempt)
        raise GeminiError(f"Gemini call failed after {retries + 1} attempt(s): {last_error}")

    def generate_text(self, prompt: str, retries: int = 1) -> str:
        return self._generate_with_retry(prompt, retries)

    def generate_json(self, prompt: str, retries: int = 1):
        text = self._generate_with_retry(prompt, retries)
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Gemini call returned invalid JSON: {exc}") from exc
