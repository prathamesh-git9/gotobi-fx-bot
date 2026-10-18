NOT READY

The third revision removes the two demonstrated resend paths and the early unverified-clock short. A healthy simulated demo account with a verified clock opens and closes the long, then opens the short. It still has a **CRITICAL** route to overlapping positions: an unresolved `PLACED` long is declared missed at its scheduled exit without checking whether the order is still live; the short can then open, and the old long can fill. A filled order that closes before reconciliation also loses its saved risk amount, so its loss disappears from the R kill switch. These are simulator and code findings, not a claim about actual Exness order behavior.

## Status of the 17 findings from REPORT_2.md

`R2` means `test_recheck.py`; `R3` means `test_recheck3.py`; `A` means `test_adversarial.py`. Test names are shown to distinguish a safe inverse from an old unsafe characterization. File references point to the current revision.

| # | Status | Code and test evidence |
|---|---|---|
| 1. Real account switch | **FIXED** | `bot/engine.py:231-245,188-193` checks account and live keys every poll. R2 `test_real_account_switch_blocks_order`, `test_other_account_pauses_and_resumes_overdue_exit` passed; A's old unsafe switch assertion failed. |
| 2. Unknown fill duplicated | **PARTLY FIXED** | Intent is saved before either send (`bot/engine.py:520-524,628-633`), and pending blocks entries (`:207-209`). R3 `test_placed_order_is_never_resent_even_after_restart` and `test_post_fill_read_error_retains_intent_and_recovers_without_resend` passed. But `:655-674` overwrites the pending record's risk with `None` when a fill has already closed; R3 `test_pending_fill_then_stop_loses_saved_risk_from_r_rule` passed. Pending orders can also be released while still live (new critical issue). |
| 3. Timed exit during outage | **ACCEPTED LIMIT** | `bot/engine.py:422-443` needs the process and terminal to send a close; the server stop/target remains. A `test_disconnect_across_exit_strands_position_until_reconnect` passed. `BOT_README.md:195-197` describes this. A demo outage drill must measure the exposure. |
| 4. Short after deadline | **PARTLY FIXED** | `bot/engine.py:622-633` checks again before the synchronous send, but that call can finish after the deadline. R2 `test_short_busy_before_deadline_is_skipped` and `test_short_can_still_fill_late_when_order_send_blocks` both passed. The latter simulated a fill at fix +10 seconds. Fill timing needs a demo measurement. |
| 5. Wrong PC clock / broker offset | **PARTLY FIXED** | `bot/engine.py:281-287` only changes offset with verified time; `:601-604` skips the unverified short. R3 `test_unverified_short_is_skipped_and_preflight_not_ready` passed. The long's 30-second guard requires five advancing ticks (`:67-74`): R3 `test_unverified_fast_pc_clock_can_open_long_before_five_ticks` opened a minute early. |
| 6. Foreign position | **FIXED** | `bot/broker.py:84-92` reads all symbol positions; `bot/engine.py:202-206` blocks entry. R2 `test_foreign_position_blocks_entry` passed; A's old hedge assertion failed. This guard does not cover live, unfilled orders (new issue). |
| 7. Flat drawdown | **FIXED** | `bot/engine.py:398-415,501-507,605-611` checks equity before entry with `<=`. R2 `test_drawdown_while_flat_blocks_entry` passed; A's old unsafe assertion failed. |
| 8. Corrupt journal startup | **PARTLY FIXED** | `bot/journal.py:29-43,63-96` rejects wrong top-level shapes and recovers a backup; R3 `test_backup_preserves_halt_and_bad_shape_is_quarantined` passed. Nested fields are not validated: `{"halted":{"reason":"test"}}` reaches `bot/engine.py:179-180` and raises `KeyError`; R3 `test_malformed_nested_state_can_crash_startup_despite_schema_check` passed. |
| 9. PLACED / partial treated as complete | **PARTLY FIXED** | `bot/broker.py:38-39,178-186` classifies PLACED as unknown, and R3's no-resend test passed. `bot/engine.py:228-229` declares it missed with no order-state query; R3 `test_pending_order_is_released_at_exit_without_order_status_check` produced a short plus later long. `bot/broker.py:36,172-174` still calls DONE_PARTIAL done; R2 `test_partial_fill_is_still_classified_as_complete` passed. |
| 10. Instance lock scope | **FIXED** | `bot/main.py:127-133` takes a login/server lock in addition to the state folder lock. R2 `test_per_account_lock_excludes_second_instance` passed. Terminal-level locking remains untested. |
| 11. Minimum lot override | **NOT FIXED** | `bot/config.py:48,88` allows `below_min_lot="min"`; `bot/sizing.py:33-40` permits risk above target. R2 `test_min_lot_override_still_exceeds_risk` passed at 1.5 for a 1.0 budget. The provided config leaves this setting at the safer default `skip`. |
| 12. Sizing quote versus send quote | **PARTLY FIXED** | `bot/broker.py:142-153` now places SL/TP from the send quote; R3 `test_moved_quote_keeps_requested_stop_distance` measured 55 pips instead of the former 65. `bot/engine.py:508-524,612-633` still sizes with the earlier quote. The request price, stop and volume are not recomputed together; slippage remains a demo question. |
| 13. Missing history and performance | **PARTLY FIXED** | A history read error leaves the slot open (`bot/engine.py:350-360`); R3 `test_history_read_errors_keep_trade_open_and_block_future_entry` passed after 131 errors. If a read succeeds but omits the closing deal, `:361-369` closes the slot with unknown P&L/R after 12 polls and never revisits it. R3 `test_successful_but_incomplete_history_still_erases_r` passed. |
| 14. State growth / disk errors | **PARTLY FIXED** | `bot/journal.py:125-133` rotates events, but `:56-61,139-173` retains all slots; R2 `test_journal_slots_still_grow_without_bound` passed. `:98-105` logs a failed backup write and continues; R3 `test_failed_backup_write_can_restore_old_unhalted_state` passed after subsequent primary corruption. |
| 15. Windows recovery | **PARTLY FIXED** | `install_autostart.ps1:29-49` configures an interactive log-on task without a time limit; R2 `test_windows_launcher_has_stop_codes_and_logon_task_settings` passed. It still requires log-on after reboot. Prior `-DryRun` hit `Access denied` at `New-ScheduledTaskAction` in this environment; no reboot/task drill was possible. |
| 16. Batch restarts deliberate stop | **PARTLY FIXED** | `run_bot.bat:8-17` stops on exit 0/2; R2 launcher static test passed. Other exit codes still retry indefinitely every 30 seconds without an alert. No MT5 terminal was available for an end-to-end launcher run. |
| 17. Real-account preflight READY | **FIXED** | `bot/engine.py:694-701` blocks readiness without both live keys; R2 `test_preflight_real_account_without_both_keys_not_ready` passed. `:732-736` now also fails readiness for an unverified clock when the short is enabled; R3 `test_unverified_short_is_skipped_and_preflight_not_ready` passed. |

## Status of the seven new findings in REPORT_2.md

| Finding | Status | Evidence |
|---|---|---|
| PLACED resent | **PARTLY FIXED** | `bot/engine.py:520-524,547-552,207-229`; R2's old duplicate assertion failed, and R3 `test_placed_order_is_never_resent_even_after_restart` passed. Releasing a still-live order at exit can allow a later overlap; R3 pending-order release test passed. |
| Fill resent after position-read error | **FIXED** | `bot/engine.py:520-524` leaves durable `sending` state if `_find_ticket` fails. R2's old assertion failed; R3 `test_post_fill_read_error_retains_intent_and_recovers_without_resend` passed. Closed-before-poll accounting is a separate new issue. |
| Backup loses kill switch | **PARTLY FIXED** | `bot/journal.py:98-105` rewrites the backup on successful saves. R2's old stale-backup assertion failed; R3 backup-preserves-halt test passed. A failed backup update is only logged, and R3 failed-backup-write test recovered an old unhalted copy. |
| Short one minute early with blocked NTP | **FIXED** | `bot/engine.py:601-604,732-736` skips the short and fails preflight. R2's early-short and ready-preflight assertions failed; R3 `test_unverified_short_is_skipped_and_preflight_not_ready` passed. The long clock gap remains. |
| Valid malformed JSON crash | **PARTLY FIXED** | `bot/journal.py:29-43,69-74` rejects `{"slots":[]}`; R2's old crash assertion failed and R3 quarantine test passed. Nested halt records still crash startup in R3's malformed-nested-state test. |
| Partial fills | **NOT FIXED** | `bot/broker.py:36,172-174` still treats DONE_PARTIAL as done; R2 `test_partial_fill_is_still_classified_as_complete` passed. No live order/deal reconciliation or remainder tracking exists. |
| History errors erase risk | **PARTLY FIXED** | `bot/engine.py:350-360` retains the slot on explicit errors; R2's old erasure assertion failed and R3's 131-error inverse passed. A successful but incomplete read still erases R in R3 `test_successful_but_incomplete_history_still_erases_r`. |

## New issues and required fixes

### CRITICAL

1. **A live queued long can overlap the short.** `bot/engine.py:212-229,194-210`: the resolver checks positions and deal history but never asks whether the returned order ID is still active. At the long's exit it changes unknown to missed, releasing the entry block. In R3 `test_pending_order_is_released_at_exit_without_order_status_check`, the short opened and the simulated queued long then filled, leaving two opposing positions. **Fix:** query active orders and order history by persisted order ID; keep the block while any remainder is live, cancel it at the trade's deadline and confirm cancellation/final fills before freeing the slot. Reconcile all resulting deals and positions after cancellation.

### HIGH

2. **A stopped pending fill loses its R result.** `bot/engine.py:540-545,655-674,398-409`: intent stores the risk amount, but `_recover_from_history` replaces it with `None` when the position filled and closed between polls. R3 `test_pending_fill_then_stop_loses_saved_risk_from_r_rule` got a negative P&L with `r=None`; the 60-long kill rule ignores it. **Fix:** retain the pending record's risk, associate every entry/exit deal with the slot, and calculate R before marking closed. If risk cannot be reconstructed, block entries and demand reconciliation.

3. **A successful but incomplete history response can erase a trade permanently.** `bot/engine.py:361-369,405-409`: after 12 polls with no closing deal, the bot records unknown P&L/R, removes the open-slot block, and stops looking. R3 `test_successful_but_incomplete_history_still_erases_r` showed the closing deal later available but unused. **Fix:** keep the slot unresolved until the exit deal and final volume are accounted for; log/escalate prolonged delay without treating it as zero risk.

4. **An unverified PC clock can open the long a minute early at startup.** `bot/engine.py:67-74,280-287,495-500`: the >30-second guard needs five advancing ticks. R3 `test_unverified_fast_pc_clock_can_open_long_before_five_ticks` started just before the apparent 15:55 and opened at physical 15:54 with one lag sample. **Fix:** block the long until enough independent live tick samples establish the clock gap, or require time verification for entries. Check the gap before the first eligible send.

5. **A failed backup update can restore an unhalted state.** `bot/journal.py:98-105,83-96`: the failed backup write is logged but the primary save succeeds. If that primary subsequently corrupts, recovery accepts the older backup. R3 `test_failed_backup_write_can_restore_old_unhalted_state` reproduced the lost halt. **Fix:** persist a separate durable halt marker, or fail closed for entries after any backup failure/recovery whose freshness cannot be proven.

### MEDIUM

6. **Nested journal records can crash startup or repeated polls.** `bot/journal.py:29-43`; `bot/engine.py:179-180,311-313,429`: validation only checks that `halted` and each slot are dictionaries. R3 `test_malformed_nested_state_can_crash_startup_despite_schema_check` accepted a halt missing `at`, then raised `KeyError`. **Fix:** validate fields used for each status, date/time strings, finite numeric values, halt reason/time, and account identity before trusting or backing up a snapshot; quarantine bad data and halt new entries.

7. **`--clear-halt` cannot clear a halt caused by the R window.** `bot/main.py:115-123`; `bot/journal.py:191-195`; `bot/engine.py:405-409`: clearing resets the peak but leaves the same 60 losing records; the next entry check immediately rehalts. R3 `test_clear_halt_retriggers_on_unchanged_losing_r_window` passed. **Fix:** store an explicit, journaled reset boundary for the R window or make the command explain that the historical R condition still prevents resumption. Avoid silently defeating the risk rule.

8. **Partial execution is still taken as a complete entry.** `bot/broker.py:36,123-130,172-174`; `bot/engine.py:530-536,639-645`. R2 `test_partial_fill_is_still_classified_as_complete` passed. The broker tries RETURN after FOK/IOC; an active remainder could later fill outside the volume recorded in the slot. **Fix:** reconcile order state, cumulative deal volume, and remaining volume; cancel or manage any remainder before treating the entry as final. The live broker's filling mode determines whether this path occurs.

### LOW

9. **The minimum-lot override and journal growth remain operational hazards.** `bot/config.py:48,88`; `bot/sizing.py:33-40`; `bot/journal.py:139-173`. R2 minimum-lot and slot-growth tests passed. **Fix:** remove or prominently gate the risk-exceeding `min` option, and bound/archivize closed records while retaining the R window and audit trail. The example config uses `skip`, so the minimum-lot hazard is opt-in.

## What I ran

- `python -m pytest tests -m "not slow" -q -p no:cacheprovider --basetemp codex_audit/bot_review/pytest_base --tb=short`: **143 passed, 8 deselected**.
- `python -m pytest codex_audit/bot_review/test_recheck.py -q -p no:cacheprovider --basetemp codex_audit/bot_review/pytest_base --tb=short`: **17 passed, 8 failed**. All eight failures were old unsafe assertions contradicted by safer results; R3 contains inverse checks for them. Passing old reproductions still indicate remaining defects.
- `python -m pytest codex_audit/bot_review/test_recheck3.py -q -p no:cacheprovider --basetemp codex_audit/bot_review/pytest_base --tb=short`: **14 passed**. Several are tests that intentionally assert a dangerous observed outcome, so this is evidence, not a safety score.
- `python -m pytest codex_audit/bot_review/test_adversarial.py -q -p no:cacheprovider --basetemp codex_audit/bot_review/pytest_base --tb=short`: **5 passed, 7 failed**. Six failures were old unsafe characterization assertions now contradicted by the code. The four-month soak still cannot enter its loop because its old clock double lacks `verified()`; that is a test harness incompatibility, not a bot result.
- Slow suite not run: the fast suite and targeted reproductions established the remaining blockers. No tests were run in parallel, no packages were installed, and nothing was committed.

## What only a real demo terminal can show

- Whether Exness's selected demo symbol and execution mode ever return PLACED, DONE_PARTIAL, timeout, or delayed deal/order history; whether an order can remain live past the long exit; and whether its order ID, deal IDs, and position ID reconcile as expected. The simulator has no native pending-order book and R3 emulates this case.
- Actual short **fill** time around 09:55 JST, slippage, spread, commission, swap, stop/target placement, and long/short timed exits. The five-second check bounds the bot's pre-send time, not broker completion.
- Recovery through MT5 disconnect, process kill, reboot, account switch, and failed close with an open position. Server-side stops protect price, but the timed exit waits for the bot and terminal to return. This is an **accepted design limit** whose real exposure must be measured in the demo, not solved by another local simulator test.
- Interactive Windows autostart/log-on behavior and whether UTC correction remains verified through the intended trading windows. A reachable, agreeing pair of time servers did not create a permanent block in the simulated verified-clock sequence; actual network, broker timestamps, and Windows Scheduler need the demo drill.
