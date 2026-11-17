"""The data page opens a table in the browser and still links the Parquet file."""

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from pa_edu.browse import render_browse
from pa_edu.serve import Handler
from pa_edu.status import render_status, status_report


def _server(directory: Path) -> tuple[ThreadingHTTPServer, int]:
    Handler.root = directory
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def _rows(page: str) -> str:
    return page.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def test_status_table_name_opens_the_browser(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    pd.DataFrame({"aun": ["101260303"]}).to_parquet(refined / "lea.parquet", index=False)
    page = render_status(status_report(tmp_path))
    assert '<a href="/browse/lea.parquet">lea.parquet</a>' in page
    assert '<a href="/refined/lea.parquet">parquet</a>' in page


def test_pages_sort_and_filter(tmp_path: Path) -> None:
    path = tmp_path / "sample.parquet"
    frame = pd.DataFrame({
        "n": list(range(80)),
        "name": ["Alpha" if index % 2 == 0 else "beta" for index in range(80)],
    })
    frame.to_parquet(path, index=False)

    first = render_browse(path, {"sort": ["n"], "dir": ["asc"]})
    assert "Rows 1-50 of 80" in first
    assert "page 1 of 2" in first
    assert '<td class="num">0</td>' in _rows(first)
    assert '<td class="num">49</td>' in _rows(first)
    assert '<td class="num">50</td>' not in _rows(first)
    assert "Next" in first
    assert "Apply" not in first
    assert 'onchange="this.form.submit()"' in first
    assert 'dir=desc' in first
    assert '<span class="name">n</span>' in first
    assert 'aria-label="Sort by n">↑</a>' in first
    assert 'aria-label="Sort by name">↕</a>' in first
    assert 'aria-label="Filter n"' in first
    assert 'aria-label="Filter name"' in first
    for size in (50, 100, 150, 200, 250):
        assert f'value="{size}"' in first

    second = render_browse(path, {"page": ["2"], "sort": ["n"], "dir": ["asc"]})
    assert "Rows 51-80 of 80" in second
    assert "page 2 of 2" in second
    assert '<td class="num">50</td>' in _rows(second)
    assert '<td class="num">79</td>' in _rows(second)
    assert "Previous" in second
    assert "Next" not in second

    wide = render_browse(path, {"page_size": ["250"], "sort": ["n"], "dir": ["asc"]})
    assert "Rows 1-80 of 80" in wide
    assert _rows(wide).count("<tr>") == 80
    assert "Next" not in wide

    fallback = render_browse(path, {"page_size": ["1000"], "sort": ["n"], "dir": ["asc"]})
    assert "Rows 1-50 of 80" in fallback
    clamped = render_browse(path, {"page": ["99"], "sort": ["n"], "dir": ["asc"]})
    assert "page 2 of 2" in clamped

    filtered = render_browse(path, {"q.name": ["alpha"], "sort": ["n"], "dir": ["asc"]})
    assert "Rows 1-40 of 40" in filtered
    assert "beta" not in _rows(filtered)
    assert "q.name=alpha" in filtered
    assert 'aria-label="Filter name, contains alpha"' in filtered
    assert 'href="/refined/sample.parquet"' in filtered

    ignored = render_browse(path, {"q.missing": ["alpha"]})
    assert "Rows 1-50 of 80" in ignored
    opened = render_browse(path, {"open": ["name"]})
    assert 'name="q.name"' in opened
    assert 'aria-label="name contains"' in opened
    assert "Apply" in opened


def test_filter_is_a_literal_substring(tmp_path: Path) -> None:
    path = tmp_path / "sample.parquet"
    pd.DataFrame({
        "name": ["100% funded", "a_b", "axb", "Alpha"],
    }).to_parquet(path, index=False)

    percent = render_browse(path, {"q.name": ["%"]})
    assert "Rows 1-1 of 1" in percent
    assert "100% funded" in _rows(percent)
    assert "Alpha" not in _rows(percent)

    underscore = render_browse(path, {"q.name": ["_"]})
    assert "Rows 1-1 of 1" in underscore
    assert "a_b" in _rows(underscore)
    assert "axb" not in _rows(underscore)

    injected = render_browse(path, {"q.name": ["' OR 1=1 --"]})
    assert "No matching rows." in injected
    assert "Alpha" not in _rows(injected)


def test_nulls_stay_blank_and_text_stays_text(tmp_path: Path) -> None:
    path = tmp_path / "sample.parquet"
    frame = pd.DataFrame({
        "aun": ["101260303", "101000000"],
        "name": ["<script>", None],
        "amount": pd.Series([0, pd.NA], dtype="Int64"),
    })
    frame.to_parquet(path, index=False)
    page = render_browse(path, {"sort": ["aun"], "dir": ["asc"]})
    body = _rows(page)
    assert "<td>101260303</td>" in body
    assert "1.01260303" not in page
    assert "&lt;script&gt;" in body
    assert "<script>" not in page
    assert '<td class="num">0</td>' in body
    assert '<td class="num"></td>' in body
    assert "<td></td>" in body
    assert ">None<" not in body
    assert "NaN" not in body
    assert body.find(">101000000<") < body.find(">101260303<")


def test_sort_puts_nulls_last(tmp_path: Path) -> None:
    path = tmp_path / "sample.parquet"
    pd.DataFrame({"name": ["b", None, "a"]}).to_parquet(path, index=False)
    ascending = _rows(render_browse(path, {"sort": ["name"], "dir": ["asc"]}))
    assert ascending.find(">a<") < ascending.find(">b<") < ascending.find("<td></td>")
    descending = _rows(render_browse(path, {"sort": ["name"], "dir": ["desc"]}))
    assert descending.find(">b<") < descending.find(">a<") < descending.find("<td></td>")
    assert 'aria-label="Sort by name">↑</a>' in render_browse(path, {"sort": ["name"], "dir": ["asc"]})
    assert 'aria-label="Sort by name">↓</a>' in render_browse(path, {"sort": ["name"], "dir": ["desc"]})


def test_column_filters_are_anded(tmp_path: Path) -> None:
    path = tmp_path / "sample.parquet"
    pd.DataFrame({
        "name": ["Alpha", "Alpha", "beta"],
        "county": ["Allegheny", "Erie", "Allegheny"],
    }).to_parquet(path, index=False)

    both = render_browse(path, {"q.name": ["alpha"], "q.county": ["erie"]})
    assert "Rows 1-1 of 1" in both
    body = _rows(both)
    assert "Erie" in body
    assert "Allegheny" not in body
    assert "beta" not in body
    assert "q.name=alpha" in both
    assert "q.county=erie" in both

    opened = render_browse(path, {"q.name": ["alpha"], "q.county": ["erie"], "open": ["name"]})
    assert 'href="/browse/sample.parquet?q.county=erie"' in opened
    assert 'name="q.name"' in opened
    assert 'value="alpha"' in opened


def test_browse_route_serves_a_page_and_rejects_other_paths(tmp_path: Path) -> None:
    refined = tmp_path / "refined"
    refined.mkdir()
    payload = pd.DataFrame({"aun": ["101260303"], "name": ["Alpha"]})
    payload.to_parquet(refined / "lea.parquet", index=False)
    (refined / "broken.parquet").write_bytes(b"not parquet")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "index.json").write_text("WORKBOOK-SENTINEL")
    server, port = _server(refined)
    try:
        home = urlopen(f"http://127.0.0.1:{port}/").read().decode()
        assert 'href="/browse/lea.parquet"' in home
        assert 'href="/refined/lea.parquet"' in home
        assert "WORKBOOK-SENTINEL" not in home
        page = urlopen(f"http://127.0.0.1:{port}/browse/lea.parquet")
        body = page.read().decode()
        assert page.status == 200
        assert "text/html" in page.headers["Content-Type"]
        assert page.headers["Cache-Control"] == "no-store"
        assert "Alpha" in body
        assert 'href="/refined/lea.parquet"' in body
        assert urlopen(f"http://127.0.0.1:{port}/refined/lea.parquet").read() == (refined / "lea.parquet").read_bytes()
        head = urlopen(Request(f"http://127.0.0.1:{port}/browse/lea.parquet", method="HEAD"))
        assert head.status == 200
        assert head.read() == b""
        broken = urlopen(f"http://127.0.0.1:{port}/browse/broken.parquet").read().decode()
        assert "could not be read" in broken
        assert "Traceback" not in broken
        assert str(tmp_path) not in broken
        assert 'href="/refined/broken.parquet"' in broken
        for path in (
            "/browse/../raw/index.json",
            "/browse/%2e%2e/raw/index.json",
            "/browse/.lea.parquet.tmp",
            "/browse/missing.parquet",
            "/browse/",
        ):
            try:
                urlopen(f"http://127.0.0.1:{port}{path}")
            except Exception as error:
                assert getattr(error, "code", None) == 404
            else:
                raise AssertionError(f"{path} was served")
    finally:
        server.shutdown()
