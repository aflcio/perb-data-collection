from perb_data_collection.collectors.nmb_representation_determinations import LISTING_URL, discover_year_page_urls, parse_determinations_table


def test_discovers_calendar_and_fiscal_year_pages() -> None:
    html = '<a href="2019-determinations/">2019</a><a href="fy2026-determinations/">FY26</a><a href="about/">About</a>'
    assert discover_year_page_urls(html) == [f"{LISTING_URL}2019-determinations/", f"{LISTING_URL}fy2026-determinations/"]


def test_parses_header_drift_and_multi_craft_case() -> None:
    html = '''<table><tr><th>Page Cite</th><th>Date</th><th>Case</th><th>Carrier</th><th>Union</th><th>Craft/Class</th><th>Disposition</th><th>53 NMB Number</th></tr>
    <tr><td><a href="/docs/r7634.pdf">R-7634</a></td><td>10/02/24</td><td>R-7634 (NMB File No. CR-7253)</td><td>TGS Cedar Port Railroad, LLC</td><td>BLET</td><td>Train and Engine Service Employees</td><td>Certification</td><td>53 NMB 12</td></tr>
    <tr><td>R-7634</td><td>10/02/24</td><td>R-7634</td><td>TGS Cedar Port Railroad, LLC</td><td>BLET</td><td>Dispatchers</td><td>Dismissal</td><td>53 NMB 13</td></tr></table>'''
    rows = parse_determinations_table(html, source_page_url=f"{LISTING_URL}fy2026-determinations/", scraped_at="2026-09-03T00:00:00+00:00")
    assert len(rows) == 2
    assert rows[0]["case_cross_references"] == "CR-7253"
    assert rows[0]["canonical_case_type"] == "CERTIFICATION"
    assert rows[0]["source_url"] == "https://nmb.gov/docs/r7634.pdf"
    assert rows[1]["canonical_case_type"] == ""
    assert rows[1]["fiscal_year"] == "2026"
