# Ohio SERB (CBA archive + Clearinghouse)

**Status:** `planned`  
**Collector:** none yet
**Source:** https://serb.ohio.gov CBA DataTable archive; Clearinghouse by request  
**Grain:** CBA table: one row per contract filing (~29,403 structured rows verified in-browser).

## Notes

- Prefer the public CBA DataTable (employer, union, unit code, size, dates) over the Clearinghouse request form for bulk work.
- Curl often 404s; browser works. Plan an oneshot / Playwright harvest before a scheduled collector.
- Clearinghouse remains useful for custom wage / pre-2000 extracts via request.
- **Representation relevance (2026-08-26):** Counts as exclusive-rep evidence the same way eCommons PERB CBAs / NYC OCB do (who represents which public unit). Top remaining greenfield in [representation-gaps-2026-08-26.md](../representation-gaps-2026-08-26.md). Soft bot gate only; resume with off-host Chrome dump → harvest file → oneshot ACE load. No Prefect cron until egress clears.
- Archive URL still serving the DataTable as of 2026-08-26: https://serb.ohio.gov/view-document-archive/collective-bargaining-agreements
