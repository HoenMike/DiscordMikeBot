"""
features/watch/scheduler.py - Watch scheduler engine with bounded concurrency,
delta-first execution, silent baseline first run, and offline catch-up protection.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

from discord.ext import commands, tasks

import config
from features.watch.constants import VALID_CADENCE_HOURS
from features.watch.evaluator import evaluate_candidates
from features.watch.manager import watch_manager
from features.watch.models import (
    EvaluationResult,
    EvaluationStatus,
    RunStatus,
    SearchResult,
    WatchDefinition,
    WatchResult,
    WatchRun,
    WatchStatus,
)
from features.watch.notifier import send_watch_notification
from features.watch.search import (
    BraveNotConfiguredError,
    BraveSearchProvider,
    BudgetExhaustedError,
    SearchCache,
    SearchError,
)


class WatchScheduler:
    """
    Periodic task loop that executes due Watches using bounded concurrency and delta-first pipeline.
    """

    def __init__(self, bot: commands.Bot, search_provider: Optional[BraveSearchProvider] = None):
        self.bot = bot
        self.search_provider = search_provider or BraveSearchProvider()
        self.search_cache = SearchCache(ttl_hours=getattr(config, "WATCH_SEARCH_CACHE_HOURS", 6))
        self._concurrency_semaphore = asyncio.Semaphore(
            getattr(config, "WATCH_MAX_CONCURRENT_RUNS", 2)
        )
        self._in_flight_tasks: Set[asyncio.Task] = set()
        self._running_watch_ids: Set[int] = set()
        self._lock = asyncio.Lock()
        self._manual_cooldowns: Dict[int, float] = {}  # user_id -> monotonic time

    def start(self) -> None:
        if not self.heartbeat_loop.is_running():
            self.heartbeat_loop.start()

    async def stop(self) -> None:
        if self.heartbeat_loop.is_running():
            self.heartbeat_loop.cancel()

        # Cancel and await all in-flight execution tasks
        tasks_to_cancel = set(self._in_flight_tasks)
        for t in tasks_to_cancel:
            t.cancel()

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._in_flight_tasks.clear()
        self._running_watch_ids.clear()

        # Close search provider session if owned
        if self.search_provider:
            await self.search_provider.close()

    @tasks.loop(minutes=15)
    async def heartbeat_loop(self) -> None:
        """Periodic scheduler wake-up check for due watches."""
        if not getattr(config, "WATCH_ENABLED", True):
            return
        try:
            await self.check_and_run_due_watches()
        except Exception as e:
            print(f"⚠️ [WatchScheduler] Lỗi trong heartbeat loop: {e}", flush=True)

    @heartbeat_loop.before_loop
    async def before_heartbeat(self) -> None:
        await self.bot.wait_until_ready()

    async def check_and_run_due_watches(self) -> int:
        """Finds all due watches and schedules them bounded by concurrency semaphore."""
        due_watches = await watch_manager.get_due_watches(limit=20)
        spawned = 0
        for watch in due_watches:
            if watch.id in self._running_watch_ids:
                continue

            task = asyncio.create_task(self._safe_execute_watch_wrapper(watch))
            self._in_flight_tasks.add(task)
            self._running_watch_ids.add(watch.id)
            task.add_done_callback(lambda t, wid=watch.id: self._task_done_callback(t, wid))
            spawned += 1

        return spawned

    def _task_done_callback(self, task: asyncio.Task, watch_id: int) -> None:
        self._in_flight_tasks.discard(task)
        self._running_watch_ids.discard(watch_id)

    async def _safe_execute_watch_wrapper(self, watch: WatchDefinition, is_manual: bool = False) -> WatchRun:
        async with self._concurrency_semaphore:
            return await self.execute_watch(watch, is_manual=is_manual)

    def calculate_next_run(self, cadence_hours: int, from_time: Optional[datetime] = None) -> str:
        base = from_time or datetime.now(timezone.utc)
        next_dt = base + timedelta(hours=cadence_hours)
        return next_dt.isoformat()

    async def execute_watch(self, watch: WatchDefinition, is_manual: bool = False) -> WatchRun:
        """
        Full Watch execution lifecycle:
        1. First run = Silent baseline (persists existing results, builds compact state, NO NOTIFICATION).
        2. Delta-first: Checks pending unevaluated candidates first. If none, checks budget & searches.
        3. If zero new results: updates schedule, saves run (no_change), NO Gemini, NO notification.
        4. If new results: calls AI Evaluator with prompt-injection defense.
        5. If meaningful change: notifies channel with idempotency check.
        """
        t_start = time.monotonic()
        # Always reload fresh watch state from database to ensure up-to-date last_checked_at and status
        fresh_watch = await watch_manager.get_watch(watch.id)
        if fresh_watch:
            watch = fresh_watch

        now_dt = datetime.now(timezone.utc)
        started_at = now_dt.isoformat()
        cadence = max(getattr(config, "WATCH_MIN_INTERVAL_HOURS", 4), watch.cadence_hours)
        next_run_at = self.calculate_next_run(cadence, from_time=now_dt)

        is_first_run = (watch.last_checked_at is None)

        # -------------------------------------------------------------
        # STEP 1: FIRST RUN = BASELINE
        # -------------------------------------------------------------
        if is_first_run:
            search_performed = 0
            cache_hit = 0
            search_result_count = 0
            results: List[SearchResult] = []
            error_text = None

            try:
                # Check budget gate
                can_search, usage, reason = await watch_manager.check_budget_gate()
                if not can_search:
                    run = WatchRun(
                        watch_id=watch.id,
                        started_at=started_at,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        status=RunStatus.BUDGET_EXHAUSTED.value,
                        search_performed=0,
                        duration_ms=round((time.monotonic() - t_start) * 1000, 1),
                        error_text=reason,
                    )
                    await watch_manager.save_run(run)
                    await watch_manager.update_watch_schedule_and_state(
                        watch.id, next_run_at=next_run_at, last_checked_at=started_at
                    )
                    return run

                # Check cache
                cached = await self.search_cache.get(watch.search_query)
                if cached is not None:
                    results = cached
                    cache_hit = 1
                    await watch_manager.increment_usage(cache_hits=1)
                else:
                    results = await self.search_provider.search(watch.search_query, limit=10)
                    search_performed = 1
                    await self.search_cache.set(watch.search_query, results)
                    await watch_manager.increment_usage(search_requests=1)

                search_result_count = len(results)
                # Persist baseline results directly as discovered
                await watch_manager.save_new_results(
                    watch.id, results, initial_status=EvaluationStatus.EVALUATED_MEANINGFUL.value
                )

                # Initialize compact state
                baseline_state = {
                    "summary": f"Mốc theo dõi ban đầu được thiết lập với {len(results)} kết quả hiện có.",
                    "known_facts": [r.title for r in results[:5]],
                    "known_entities": [],
                    "last_major_change": "Thiết lập mốc theo dõi ban đầu",
                    "last_evaluated_at": started_at,
                }
                import json
                state_json_str = json.dumps(baseline_state, ensure_ascii=False)

                await watch_manager.update_watch_schedule_and_state(
                    watch_id=watch.id,
                    next_run_at=next_run_at,
                    last_checked_at=started_at,
                    state_json=state_json_str,
                    reset_failure=True,
                )

                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.BASELINE.value,
                    search_performed=search_performed,
                    cache_hit=cache_hit,
                    search_result_count=search_result_count,
                    new_result_count=search_result_count,
                    ai_called=0,
                    meaningful_change=0,
                    notification_sent=0,
                    duration_ms=duration_ms,
                    error_text=None,
                )
                await watch_manager.save_run(run)
                return run

            except BraveNotConfiguredError as bnc:
                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                await watch_manager.update_watch_schedule_and_state(
                    watch.id,
                    next_run_at=next_run_at,
                    status=WatchStatus.CONFIG_ERROR.value,
                    last_error=str(bnc),
                )
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.SEARCH_FAILED.value,
                    duration_ms=duration_ms,
                    error_text=str(bnc),
                )
                await watch_manager.save_run(run)
                return run
            except Exception as e:
                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                await watch_manager.update_watch_schedule_and_state(
                    watch.id,
                    next_run_at=next_run_at,
                    failure_count_delta=1,
                    last_error=str(e),
                )
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.SEARCH_FAILED.value,
                    duration_ms=duration_ms,
                    error_text=str(e),
                )
                await watch_manager.save_run(run)
                return run

        # -------------------------------------------------------------
        # STEP 2: SUBSEQUENT RUNS (DELTA-FIRST)
        # -------------------------------------------------------------
        pending_candidates: List[Any] = await watch_manager.get_pending_results(watch.id)
        candidates_to_evaluate: List[Any] = []
        search_performed = 0
        cache_hit = 0
        search_result_count = 0
        new_result_count = 0

        if pending_candidates:
            # Re-evaluate without re-search! Saves Brave quota.
            candidates_to_evaluate = pending_candidates
        else:
            # Need to search for new results
            can_search, usage, reason = await watch_manager.check_budget_gate()
            if not can_search:
                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.BUDGET_EXHAUSTED.value,
                    search_performed=0,
                    duration_ms=duration_ms,
                    error_text=reason,
                )
                await watch_manager.save_run(run)
                await watch_manager.update_watch_schedule_and_state(
                    watch.id, next_run_at=next_run_at, last_checked_at=started_at
                )
                return run

            try:
                cached = await self.search_cache.get(watch.search_query)
                if cached is not None:
                    results = cached
                    cache_hit = 1
                    await watch_manager.increment_usage(cache_hits=1)
                else:
                    results = await self.search_provider.search(watch.search_query, limit=10)
                    search_performed = 1
                    await self.search_cache.set(watch.search_query, results)
                    await watch_manager.increment_usage(search_requests=1)

                search_result_count = len(results)
                newly_discovered = await watch_manager.save_new_results(
                    watch.id, results, initial_status=EvaluationStatus.DISCOVERED.value
                )
                new_result_count = len(newly_discovered)
                candidates_to_evaluate = newly_discovered

            except BraveNotConfiguredError as bnc:
                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                await watch_manager.update_watch_schedule_and_state(
                    watch.id,
                    next_run_at=next_run_at,
                    status=WatchStatus.CONFIG_ERROR.value,
                    last_error=str(bnc),
                )
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.SEARCH_FAILED.value,
                    duration_ms=duration_ms,
                    error_text=str(bnc),
                )
                await watch_manager.save_run(run)
                return run
            except Exception as e:
                duration_ms = round((time.monotonic() - t_start) * 1000, 1)
                await watch_manager.update_watch_schedule_and_state(
                    watch.id,
                    next_run_at=next_run_at,
                    failure_count_delta=1,
                    last_error=str(e),
                )
                run = WatchRun(
                    watch_id=watch.id,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.SEARCH_FAILED.value,
                    duration_ms=duration_ms,
                    error_text=str(e),
                )
                await watch_manager.save_run(run)
                return run

        # If zero candidate results to evaluate -> NO CHANGE!
        if not candidates_to_evaluate:
            duration_ms = round((time.monotonic() - t_start) * 1000, 1)
            await watch_manager.update_watch_schedule_and_state(
                watch_id=watch.id,
                next_run_at=next_run_at,
                last_checked_at=started_at,
                reset_failure=True,
            )
            run = WatchRun(
                watch_id=watch.id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                status=RunStatus.NO_CHANGE.value,
                search_performed=search_performed,
                cache_hit=cache_hit,
                search_result_count=search_result_count,
                new_result_count=0,
                ai_called=0,
                meaningful_change=0,
                notification_sent=0,
                duration_ms=duration_ms,
            )
            await watch_manager.save_run(run)
            return run

        # -------------------------------------------------------------
        # STEP 3: AI EVALUATION (ONLY FOR CANDIDATE RESULTS)
        # -------------------------------------------------------------
        ai_enabled = getattr(config, "WATCH_AI_EVAL_ENABLED", True) and bool(
            getattr(config, "GEMINI_API_KEY", "")
        )

        candidate_fps = [c.fingerprint for c in candidates_to_evaluate]

        if not ai_enabled:
            # Fallback when AI eval is disabled
            await watch_manager.mark_results_status(
                watch.id, candidate_fps, EvaluationStatus.EVALUATED_IRRELEVANT.value
            )
            duration_ms = round((time.monotonic() - t_start) * 1000, 1)
            await watch_manager.update_watch_schedule_and_state(
                watch_id=watch.id,
                next_run_at=next_run_at,
                last_checked_at=started_at,
            )
            run = WatchRun(
                watch_id=watch.id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                status=RunStatus.SUCCESS.value,
                search_performed=search_performed,
                cache_hit=cache_hit,
                search_result_count=search_result_count,
                new_result_count=new_result_count,
                ai_called=0,
                meaningful_change=0,
                notification_sent=0,
                duration_ms=duration_ms,
            )
            await watch_manager.save_run(run)
            return run

        # AI Evaluation attempt
        try:
            eval_result: EvaluationResult = await evaluate_candidates(watch, candidates_to_evaluate)
            await watch_manager.increment_usage(ai_evaluations=1)
        except Exception as ai_err:
            # AI FAILED: Candidate results stay discovered!
            duration_ms = round((time.monotonic() - t_start) * 1000, 1)
            await watch_manager.update_watch_schedule_and_state(
                watch_id=watch.id,
                next_run_at=next_run_at,
                last_checked_at=started_at,
                failure_count_delta=1,
                last_error=f"AI Evaluator: {ai_err}",
            )
            run = WatchRun(
                watch_id=watch.id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                status=RunStatus.AI_FAILED.value,
                search_performed=search_performed,
                cache_hit=cache_hit,
                search_result_count=search_result_count,
                new_result_count=new_result_count,
                ai_called=1,
                meaningful_change=0,
                notification_sent=0,
                duration_ms=duration_ms,
                error_text=str(ai_err),
            )
            await watch_manager.save_run(run)
            return run

        # AI EVALUATION SUCCEEDED
        # Merge updated state
        current_state = watch.get_state()
        if eval_result.updated_state:
            current_state.update(eval_result.updated_state)
        current_state["last_evaluated_at"] = started_at
        import json
        updated_state_str = json.dumps(current_state, ensure_ascii=False)

        notification_sent = 0
        new_status = None
        last_notified_at = watch.last_notified_at

        # Determine which candidates are relevant
        relevant_candidates = []
        if eval_result.relevant_result_indices:
            for idx in eval_result.relevant_result_indices:
                if 0 <= idx < len(candidates_to_evaluate):
                    relevant_candidates.append(candidates_to_evaluate[idx])
        if not relevant_candidates and candidates_to_evaluate:
            relevant_candidates = candidates_to_evaluate[:3]

        if eval_result.meaningful_change:
            # Check terminal condition
            is_terminal = (
                watch.stop_after_trigger
                and (eval_result.condition_satisfied or eval_result.suggest_complete)
            )

            # Mark relevant results as evaluated_meaningful
            rel_fps = [c.fingerprint for c in relevant_candidates]
            other_fps = [fp for fp in candidate_fps if fp not in rel_fps]

            await watch_manager.mark_results_status(
                watch.id,
                rel_fps,
                EvaluationStatus.EVALUATED_MEANINGFUL.value,
                event_fingerprint=eval_result.event_fingerprint,
            )
            if other_fps:
                await watch_manager.mark_results_status(
                    watch.id, other_fps, EvaluationStatus.EVALUATED_IRRELEVANT.value
                )

            # Send Discord notification
            sent = await send_watch_notification(
                bot=self.bot,
                watch=watch,
                eval_result=eval_result,
                sources=relevant_candidates,
                is_terminal=is_terminal,
            )
            if sent:
                notification_sent = 1
                last_notified_at = started_at
                await watch_manager.increment_usage(notifications_sent=1)
                # Mark as notified
                await watch_manager.mark_results_status(
                    watch.id, rel_fps, EvaluationStatus.NOTIFIED.value
                )

            if is_terminal:
                new_status = WatchStatus.COMPLETED.value
                next_run_at = None
        else:
            # Not meaningful -> mark all candidates evaluated_irrelevant
            await watch_manager.mark_results_status(
                watch.id, candidate_fps, EvaluationStatus.EVALUATED_IRRELEVANT.value
            )

        duration_ms = round((time.monotonic() - t_start) * 1000, 1)

        await watch_manager.update_watch_schedule_and_state(
            watch_id=watch.id,
            next_run_at=next_run_at,
            last_checked_at=started_at,
            last_notified_at=last_notified_at,
            state_json=updated_state_str,
            status=new_status,
            reset_failure=True,
        )

        run = WatchRun(
            watch_id=watch.id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            status=RunStatus.SUCCESS.value,
            search_performed=search_performed,
            cache_hit=cache_hit,
            search_result_count=search_result_count,
            new_result_count=new_result_count,
            ai_called=1,
            meaningful_change=1 if eval_result.meaningful_change else 0,
            notification_sent=notification_sent,
            duration_ms=duration_ms,
        )
        await watch_manager.save_run(run)
        return run
