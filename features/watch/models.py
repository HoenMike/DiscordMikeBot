"""
features/watch/models.py - Data models, dataclasses, and enums for the Watch engine.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class WatchStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DISABLED = "disabled"
    CONFIG_ERROR = "config_error"


class EvaluationStatus(str, Enum):
    DISCOVERED = "discovered"
    EVALUATED_IRRELEVANT = "evaluated_irrelevant"
    EVALUATED_MEANINGFUL = "evaluated_meaningful"
    NOTIFIED = "notified"


class RunStatus(str, Enum):
    SUCCESS = "success"
    NO_CHANGE = "no_change"
    BASELINE = "baseline"
    AI_FAILED = "ai_failed"
    SEARCH_FAILED = "search_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class SearchResult:
    """Normalized search result item independent of search provider."""
    title: str
    url: str
    canonical_url: str
    snippet: str
    source_domain: str
    published_at: Optional[str] = None
    fingerprint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchDefinition:
    """Persistent Watch goal/topic definition."""
    owner_user_id: int
    channel_id: int
    title: str
    search_query: str
    guild_id: Optional[int] = None
    condition_prompt: Optional[str] = None
    status: str = WatchStatus.ACTIVE.value
    cadence_hours: int = 24
    id: Optional[int] = None
    next_run_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_notified_at: Optional[str] = None
    state_json: str = "{}"
    notify_only_on_change: int = 1
    stop_after_trigger: int = 0
    failure_count: int = 0
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def get_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_json) if self.state_json else {}
        except Exception:
            return {}

    def set_state(self, state: Dict[str, Any]) -> None:
        self.state_json = json.dumps(state, ensure_ascii=False)


@dataclass
class WatchResult:
    """Persistent discovered/evaluated search result record."""
    watch_id: int
    fingerprint: str
    url: str
    canonical_url: str
    title: str
    snippet: str
    source_domain: str
    published_at: Optional[str] = None
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evaluation_status: str = EvaluationStatus.DISCOVERED.value
    event_fingerprint: Optional[str] = None
    metadata_json: str = "{}"
    id: Optional[int] = None


@dataclass
class WatchRun:
    """Observability record of a single Watch execution."""
    watch_id: int
    started_at: str
    finished_at: str
    status: str
    search_performed: int = 0
    cache_hit: int = 0
    search_result_count: int = 0
    new_result_count: int = 0
    ai_called: int = 0
    meaningful_change: int = 0
    notification_sent: int = 0
    duration_ms: float = 0.0
    error_text: Optional[str] = None
    id: Optional[int] = None


@dataclass
class SearchUsage:
    """Persistent monthly search & evaluation metrics."""
    month_key: str
    search_requests: int = 0
    cache_hits: int = 0
    ai_evaluations: int = 0
    notifications_sent: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class EvaluationResult:
    """Structured AI classifier output."""
    meaningful_change: bool = False
    significance: str = "low"  # low, medium, high
    summary: str = ""
    reason: str = ""
    relevant_result_indices: List[int] = field(default_factory=list)
    condition_satisfied: bool = False
    suggest_complete: bool = False
    event_fingerprint: Optional[str] = None
    updated_state: Dict[str, Any] = field(default_factory=dict)
