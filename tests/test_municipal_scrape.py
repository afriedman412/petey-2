"""The municipal scraper for the flat-structure benchmark (2026-10-27, Andrew: "can you try scraping municipal sites?"):
which links are followed, which count as PDFs, and what one site is."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "acquisition"))

import municipal_scrape as M  # noqa: E402


def test_site_key_spans_www_and_subdomains_but_not_other_localities():
    assert M.site_key("www.cityofx.gov") == M.site_key("permits.cityofx.gov") == "cityofx.gov"
    assert M.site_key("www.co.lake.il.us") == "co.lake.il.us"       # locality .us names are kept whole
    assert M.site_key("co.lake.il.us") != M.site_key("co.cook.il.us")


def test_pdf_links_include_civicplus_and_granicus_documents():
    for u in ("https://x.gov/files/permit.pdf", "https://x.gov/DocumentCenter/View/59/Building-Permit",
              "https://x.gov/home/showpublisheddocument/29276/6391"):
        assert M.PDF_HREF.search(u)
    assert not M.PDF_HREF.search("https://x.gov/departments/planning")


def test_meeting_papers_and_images_are_skipped():
    assert M.SKIP_HREF.search("https://x.gov/files/2026-agenda.pdf Council Agenda")
    assert M.SKIP_HREF.search("https://x.gov/img/logo.png")
    assert not M.SKIP_HREF.search("https://x.gov/files/sign-permit-application.pdf Sign Permit")


def test_form_links_are_checked_first():
    assert M.FORMISH.search("Nuisance Complaint Form.pdf") and not M.FORMISH.search("2026-Garbage-calendar.pdf")


def test_dated_editions_are_one_form_by_text_not_name():
    # 2026-10-28: the name says nothing ("download.pdf"); page 1's words do
    words = "application for a business license name of business address city state zip phone owner".split()
    a = frozenset(words + ["2024"]); b = frozenset(words + ["2025"])
    assert M.same_form(a, b)
    assert not M.same_form(a, frozenset("sign permit application sign size location height illumination".split()))


def _old_test_dated_editions_of_one_form_share_a_file_key():
    # greenecountyny.gov, pilot 2026-10-27: the 2024 and 2025 job applications were both kept
    a = M.file_key("https://x.gov/files/GC-HR-EMPLOYMENT-APPLICATION-2025.pdf")
    assert a == M.file_key("https://x.gov/docs/GC-HR-EMPLOYMENT-APPLICATION-2024.pdf")
    assert a != M.file_key("https://x.gov/files/SIGN-PERMIT-2025.pdf")


def test_pdfs_served_without_a_pdf_name():
    # state tax pages, 2026-10-28: Indiana, Alaska, Iowa, North Carolina
    for u in ("https://forms.in.gov/Download.aspx?id=15210", "https://tax.alaska.gov/programs/documentviewer/viewer.aspx?ID=1",
              "https://revenue.iowa.gov/media/1234/download?inline", "https://www.ncdor.gov/documents/files/d-400/open"):
        assert M.PDF_HREF.search(u)


class _Page:
    def __init__(self, text, url="https://dmv.example.gov/forms/"):
        self.text, self.content, self.url = text, text.encode(), url
        self.headers = {"content-type": "text/html"}


def test_links_strip_inner_whitespace_and_find_embedded_pdfs():
    # SC DMV hrefs with newlines; MN / TN DMV PDF addresses inside escaped JSON (2026-10-28)
    page = _Page('<a href="/files/\n  MV-1.pdf ">MV-1</a>'
                 '<div data-x="{&#34;url&#34;:&#34;https:\\/\\/assets.dps.mn.gov\\/a\\/PS2000.pdf&#34;}"></div>')
    got = [u for u, _ in M.links(page)]
    assert "https://dmv.example.gov/files/MV-1.pdf" in got
    assert "https://assets.dps.mn.gov/a/PS2000.pdf" in got


def test_more_pdf_link_shapes():
    for u in ("https://dor.georgia.gov/document/document/mv-1/download", "https://mva.maryland.gov/media/1234",
              "https://dol.wa.gov/forms/view/420073", "https://www.dmv.ca.gov/portal/form/reg-343/"):
        assert M.PDF_HREF.search(u)


def test_links_from_a_search_api_and_other_country_pdf_shapes():
    # GOV.UK's search API lists DVLA / DWP form pages as JSON (2026-10-28)
    page = _Page('{"results": [{"link": "/government/publications/v1-application", "title": "V1"}]}',
                 "https://www.gov.uk/api/search.json?x=1")
    page.headers = {"content-type": "application/json"}
    assert M.links(page) == [("https://www.gov.uk/government/publications/v1-application", "form")]
    assert M.PDF_HREF.search("https://www.jamaicatax.gov.jm/documents/10181/1/IT01.pdf/0a1b2c3d-1111-2222")
    assert M.PDF_HREF.search("https://cfr.forms.gov.ab.ca/Form/TRA0012")


def test_bynder_pdfs_in_page_data():
    # Schwab's /resource/<form> pages, 2026-10-28: the PDF is bynder.schwab.com/m/<id> inside escaped JSON
    page = _Page('<script>{"src":"https:\\/\\/bynder.schwab.com\\/m\\/b2b1da5f520702d#toolbar=1"}</script>')
    assert "https://bynder.schwab.com/m/b2b1da5f520702d" in [u for u, _ in M.links(page)]
    assert M.PDF_HREF.search("https://bynder.schwab.com/m/b2b1da5f520702d")


def test_publisher_pages_picked_by_category():
    import publisher_scrape as P
    seeds = [{"category": "finance", "index_url": "a", "pdf_links": "direct"},
             {"category": "finance", "index_url": "b", "pdf_links": "js or blocked"},
             {"category": "dmv", "index_url": "c", "pdf_links": "direct"},
             {"category": "finance", "index_url": "d", "pdf_links": "one level down"}]
    assert [s["index_url"] for s in P.pick(seeds, {"d"}, {"finance"})] == ["a"]
    assert [s["index_url"] for s in P.pick(seeds, set(), set())] == ["a", "c", "d"]
