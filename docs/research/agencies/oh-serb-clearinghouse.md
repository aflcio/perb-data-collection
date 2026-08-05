# Ohio SERB (CBA archive + Clearinghouse)

**Status:** `planned`  
**Collector:** none yet
**Source:** https://serb.ohio.gov CBA DataTable archive; Clearinghouse by request  
**Grain:** CBA table: one row per contract filing (~29,403 structured rows verified in-browser).

## Notes

- Prefer the public CBA DataTable (employer, union, unit code, size, dates) over the Clearinghouse request form for bulk work.
- Curl often 404s; browser works. Plan an oneshot / Playwright harvest before a scheduled collector.
- Clearinghouse remains useful for custom wage / pre-2000 extracts via request.

