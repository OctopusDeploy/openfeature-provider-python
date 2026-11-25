import logging
import threading
from datetime import timedelta

from octopus_openfeature_provider._feature_flag_api_client import (
    ContentHashCheckError,
    FeatureFlagApiClient,
)
from octopus_openfeature_provider._feature_flag_evaluator import FeatureFlagEvaluator

_logger = logging.getLogger(__name__)

POLLING_THREAD_NAME = "octopus-openfeature-provider-polling"

_INITIAL_FETCH_FAILED = "Failed to retrieve feature manifest during initialization. Falling back to no evaluations, defaults will be used during evaluation."
_REFRESH_FAILED = (
    "Failed to retrieve updated feature manifest. Retaining the existing evaluations."
)
_FETCH_WITHOUT_MANIFEST_FAILED = "Failed to retrieve feature manifest. No evaluations have been retrieved yet, defaults will be used during evaluation."


class FeatureFlagEvaluatorCache:
    """Holds the evaluator the provider resolves flags against, and keeps it
    updated by polling the feature flags service.

    Until a fetch succeeds it holds an empty evaluator with no content hash,
    which the provider treats as not ready. A failed refresh keeps the last
    good evaluator.
    """

    def __init__(
        self, api_client: FeatureFlagApiClient, poll_interval: timedelta
    ) -> None:
        self._api_client = api_client
        self._poll_interval_seconds = poll_interval.total_seconds()
        self._evaluator = FeatureFlagEvaluator.empty()

        # The SDK may call initialize and shutdown on different threads,
        # while the polling thread runs. The lock stops them from interfering.
        # Reads of _evaluator don't need this lock.
        self._lock = threading.Lock()
        # Set to stop the work that initialize call started: its initial fetch
        # and the polling after it. Each initialize call replaces it with a new
        # event, so a fetch or refresh left over from an earlier call can tell
        # it's been stopped, and won't install evaluations or outlive shutdown.
        self._stop_requested = threading.Event()
        self._polling_thread: threading.Thread | None = None

    def get_evaluator(self) -> FeatureFlagEvaluator:
        return self._evaluator

    def initialize(self) -> None:
        """Fetch the evaluations and start polling. Never raises."""
        with self._lock:
            previous_polling_thread = self._signal_stop()
            stop_requested = threading.Event()
            self._stop_requested = stop_requested
            self._evaluator = FeatureFlagEvaluator.empty()
            self._api_client.open()

        _join_unless_current(previous_polling_thread)

        # The initial fetch runs on the polling thread too, so every request
        # is made there and shutdown only has to wait for that thread before
        # it closes the HTTP client.
        initial_fetch_done = threading.Event()
        polling_thread = threading.Thread(
            target=self._poll,
            args=(stop_requested, initial_fetch_done),
            name=POLLING_THREAD_NAME,
            daemon=True,
        )
        with self._lock:
            if stop_requested.is_set():
                return
            polling_thread.start()
            self._polling_thread = polling_thread

        initial_fetch_done.wait()

    def shutdown(self) -> None:
        """Stop polling, wait for a fetch or refresh in flight to finish, and
        close the HTTP client if the provider created it."""
        with self._lock:
            stop_requested = self._stop_requested
            polling_thread = self._signal_stop()

        _join_unless_current(polling_thread)

        with self._lock:
            # If the cache was initialized again while this waited, that later
            # initialize call owns the HTTP client now.
            if self._stop_requested is stop_requested:
                self._api_client.close()

    def _signal_stop(self) -> threading.Thread | None:
        self._stop_requested.set()
        polling_thread = self._polling_thread
        self._polling_thread = None
        return polling_thread

    def _poll(
        self, stop_requested: threading.Event, initial_fetch_done: threading.Event
    ) -> None:
        try:
            self._initial_fetch(stop_requested)
        finally:
            initial_fetch_done.set()

        while not stop_requested.wait(self._poll_interval_seconds):
            self._refresh(stop_requested)

    def _initial_fetch(self, stop_requested: threading.Event) -> None:
        """Never raises. A failed fetch leaves the empty evaluator."""
        try:
            response = self._api_client.get_server_side_evaluations()
            if response is None:
                return
            evaluator = FeatureFlagEvaluator(response)
        except Exception:
            if not stop_requested.is_set():
                _logger.exception(_INITIAL_FETCH_FAILED)
            return

        self._install_evaluator(evaluator, stop_requested)

    def _refresh(self, stop_requested: threading.Event) -> None:
        """Never raises. A failed refresh keeps the current evaluator, and the
        next interval tries again."""
        current_evaluator = self._evaluator
        failed_message = (
            _REFRESH_FAILED
            if current_evaluator.content_hash
            else _FETCH_WITHOUT_MANIFEST_FAILED
        )
        try:
            if not self._api_client.have_features_changed(
                current_evaluator.content_hash
            ):
                return

            response = self._api_client.get_server_side_evaluations()
            if response is None:
                _logger.error(failed_message)
                return

            evaluator = FeatureFlagEvaluator(response)
        except ContentHashCheckError as error:
            if not stop_requested.is_set():
                _logger.error("%s %s", failed_message, error)
            return
        except Exception:
            if not stop_requested.is_set():
                _logger.exception(failed_message)
            return

        self._install_evaluator(evaluator, stop_requested)

    def _install_evaluator(
        self, evaluator: FeatureFlagEvaluator, stop_requested: threading.Event
    ) -> None:
        with self._lock:
            if not stop_requested.is_set():
                self._evaluator = evaluator


def _join_unless_current(thread: threading.Thread | None) -> None:
    if thread is not None and thread is not threading.current_thread():
        thread.join()
