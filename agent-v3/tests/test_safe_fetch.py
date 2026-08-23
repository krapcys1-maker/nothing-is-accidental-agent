"""Kontrdowody SSRF, redirectów, DNS pinningu i limitów odpowiedzi V3."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
from unittest import mock

import httpx
import pypdf
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import browser
import config
import db
import safe_fetch
import stages


PUBLIC_V4 = "93.184.216.34"
PUBLIC_V4_ALT = "8.8.8.8"


class FixtureStream(httpx.SyncByteStream):
    def __init__(self, *chunks: bytes):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def public_resolver(host: str, _port: int):
    return (PUBLIC_V4_ALT if host == "other.example" else PUBLIC_V4,)


class SafeURLTest(unittest.TestCase):
    def test_rejects_non_http_userinfo_port_controls_and_backslash(self) -> None:
        bad = (
            "file:///etc/passwd",
            "ftp://example.com/a",
            "https://user:pass@example.com/a",
            "https://example.com:444/a",
            "https://example.com\\@127.0.0.1/a",
            "https://example.com/a\nHost:x",
        )
        for url in bad:
            with self.subTest(url=url), self.assertRaises(safe_fetch.UnsafeURL):
                safe_fetch.normalize_url(url)

    def test_rejects_excessive_url(self) -> None:
        with self.assertRaises(safe_fetch.UnsafeURL):
            safe_fetch.normalize_url(
                "https://example.com/" + "x" * config.FETCH_MAX_URL_CHARS)

    def test_rejects_every_non_global_literal_address(self) -> None:
        bad = (
            "127.0.0.1", "0.0.0.0", "10.0.0.1", "172.16.0.1",
            "192.168.1.1", "169.254.169.254", "224.0.0.1", "::1",
            "fe80::1", "fc00::1", "::",
        )
        for address in bad:
            bracketed = f"[{address}]" if ":" in address else address
            with self.subTest(address=address), self.assertRaises(
                    safe_fetch.UnsafeURL):
                safe_fetch.validate_url(
                    f"http://{bracketed}/metadata", public_resolver)

    def test_mixed_dns_is_rejected_as_a_whole(self) -> None:
        with self.assertRaises(safe_fetch.UnsafeURL):
            safe_fetch.validate_url(
                "https://example.com/a",
                lambda *_: (PUBLIC_V4, "127.0.0.1"),
            )

    def test_public_dns_is_canonical_and_deduplicated(self) -> None:
        target = safe_fetch.validate_url(
            "HTTPS://Example.COM:443/a#fragment",
            lambda *_: (PUBLIC_V4, PUBLIC_V4, PUBLIC_V4_ALT),
        )
        self.assertEqual(target.url, "https://example.com/a")
        self.assertEqual(target.hostname, "example.com")
        self.assertEqual(set(target.ips), {PUBLIC_V4, PUBLIC_V4_ALT})


class PinnedBackendTest(unittest.TestCase):
    def test_connection_uses_literal_pinned_ip_not_hostname(self) -> None:
        class FakeBackend:
            def __init__(self):
                self.calls = []

            def connect_tcp(self, host, port, **kwargs):
                self.calls.append((host, port, kwargs))
                return "stream"

            def sleep(self, _seconds):
                pass

        fake = FakeBackend()
        backend = safe_fetch.PinnedDNSBackend(
            {"example.com": (PUBLIC_V4,)}, backend=fake)
        self.assertEqual(backend.connect_tcp("example.com", 443), "stream")
        self.assertEqual(fake.calls[0][0], PUBLIC_V4)
        with self.assertRaises(safe_fetch.UnsafeURL):
            backend.connect_tcp("not-pinned.example", 443)

    def test_httpx_pool_really_receives_pinned_backend(self) -> None:
        target = safe_fetch.ValidatedTarget(
            "https://example.com/", "https", "example.com", 443,
            (PUBLIC_V4,))
        transport = safe_fetch.pinned_transport(target)
        try:
            self.assertIsInstance(
                transport._pool._network_backend,
                safe_fetch.PinnedDNSBackend,
            )
        finally:
            transport.close()


class SafeFetcherTest(unittest.TestCase):
    def factory(self, handler, targets):
        def make(target):
            targets.append(target)
            return httpx.MockTransport(handler)
        return make

    def test_public_to_private_redirect_stops_before_second_transport(self) -> None:
        requests = []
        targets = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(
                302, headers={"Location": "http://169.254.169.254/latest"})

        fetcher = safe_fetch.SafeFetcher(
            resolver=public_resolver,
            transport_factory=self.factory(handler, targets))
        with self.assertRaises(safe_fetch.UnsafeURL):
            fetcher.get("https://example.com/start")
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(targets), 1)

    def test_each_public_redirect_is_revalidated_and_recorded(self) -> None:
        resolved = []
        targets = []

        def resolver(host, port):
            resolved.append((host, port))
            return public_resolver(host, port)

        def handler(request):
            if request.url.host == "example.com":
                return httpx.Response(
                    301, headers={"Location": "https://other.example/final"})
            return httpx.Response(
                200, headers={"Content-Type": "text/plain"},
                stream=FixtureStream(b"done"))

        response = safe_fetch.SafeFetcher(
            resolver=resolver,
            transport_factory=self.factory(handler, targets),
        ).get("https://example.com/start")
        self.assertEqual(response.text, "done")
        self.assertEqual(response.url, "https://other.example/final")
        self.assertEqual(len(response.hops), 2)
        self.assertEqual([item[0] for item in resolved],
                         ["example.com", "other.example"])
        self.assertEqual(response.resolved_ips["other.example"], [PUBLIC_V4_ALT])

    def test_repeated_host_preserves_every_dns_pin(self) -> None:
        answers = iter(((PUBLIC_V4,), (PUBLIC_V4_ALT,)))

        def handler(request):
            if request.url.path == "/start":
                return httpx.Response(
                    302, headers={"Location": "https://example.com/final"})
            return httpx.Response(
                200, headers={"Content-Type": "text/plain"},
                stream=FixtureStream(b"done"))

        response = safe_fetch.SafeFetcher(
            resolver=lambda *_args: next(answers),
            transport_factory=lambda _target: httpx.MockTransport(handler),
        ).get("https://example.com/start")
        self.assertEqual(
            response.resolved_ips["example.com"], [PUBLIC_V4, PUBLIC_V4_ALT])

    def test_https_downgrade_is_rejected(self) -> None:
        def handler(_request):
            return httpx.Response(
                302, headers={"Location": "http://other.example/final"})

        with self.assertRaises(safe_fetch.RedirectPolicyError):
            safe_fetch.SafeFetcher(
                resolver=public_resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ).get("https://example.com/start")

    def test_redirect_limit_is_hard(self) -> None:
        def handler(request):
            number = int(request.url.params.get("n", "0"))
            return httpx.Response(
                302, headers={"Location": f"https://example.com/x?n={number + 1}"})

        with self.assertRaises(safe_fetch.RedirectPolicyError):
            safe_fetch.SafeFetcher(
                resolver=public_resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
                max_redirects=2,
            ).get("https://example.com/x?n=0")

    def test_content_length_and_actual_stream_have_independent_limits(self) -> None:
        original = config.FETCH_MAX_HTML_BYTES
        config.FETCH_MAX_HTML_BYTES = 10
        try:
            declared = lambda _request: httpx.Response(
                200, headers={"Content-Type": "text/html", "Content-Length": "11"},
                stream=FixtureStream(b"x"))
            with self.assertRaises(safe_fetch.ResponseTooLarge):
                safe_fetch.SafeFetcher(
                    resolver=public_resolver,
                    transport_factory=lambda _target: httpx.MockTransport(declared),
                ).get("https://example.com/a")

            streamed = lambda _request: httpx.Response(
                200, headers={"Content-Type": "text/html"},
                stream=FixtureStream(b"x" * 6, b"x" * 5))
            with self.assertRaises(safe_fetch.ResponseTooLarge):
                safe_fetch.SafeFetcher(
                    resolver=public_resolver,
                    transport_factory=lambda _target: httpx.MockTransport(streamed),
                ).get("https://example.com/a")
        finally:
            config.FETCH_MAX_HTML_BYTES = original

    def test_compressed_response_is_rejected_and_identity_is_requested(self) -> None:
        seen = []

        def handler(request):
            seen.append(request.headers.get("accept-encoding"))
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
                stream=FixtureStream(b"not-read"),
            )

        with self.assertRaises(safe_fetch.SafeFetchError):
            safe_fetch.SafeFetcher(
                resolver=public_resolver,
                transport_factory=lambda _target: httpx.MockTransport(handler),
            ).get("https://example.com/a")
        self.assertEqual(seen, ["identity"])

    def test_content_types_have_separate_limits(self) -> None:
        self.assertLess(config.FETCH_MAX_JSON_BYTES, config.FETCH_MAX_HTML_BYTES)
        self.assertLess(config.FETCH_MAX_HTML_BYTES, config.FETCH_MAX_PDF_BYTES)


class IntegrationContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_discovery_requires_exact_search_result_not_only_host(self) -> None:
        conn = db.connect(pathlib.Path(self.temp.name) / "discovery.db")
        original_call = stages.llm.call
        try:
            def fake_call(*_args, **kwargs):
                kwargs["collect_urls"].append("https://example.com/real#result")
                return json.dumps({"sources": [
                    {"url": "https://example.com/real", "title": "real",
                     "publisher": "Example", "class": "PRIMARY",
                     "host_role": "ORIGINATING_AUTHORITY",
                     "access_claim": "FULL_TEXT_NO_LOGIN",
                     "published_at": "2026-08-21",
                     "evidence_status": "OBSERVED_CURRENT_RECORD",
                     "evidence_roles": ["CURRENT_SCALE"],
                     "answers_why": True, "has_numbers": False, "note": "fixture"},
                    {"url": "https://example.com/invented", "title": "fake",
                     "publisher": "Example", "class": "SUPPORTING",
                     "host_role": "OTHER", "access_claim": "FULL_TEXT_NO_LOGIN",
                     "published_at": "2026-08-21",
                     "evidence_status": "OBSERVED_CURRENT_RECORD",
                     "evidence_roles": ["BACKGROUND"],
                     "answers_why": False, "has_numbers": False, "note": "fixture"},
                ]})

            stages.llm.call = fake_call
            with mock.patch.object(
                config, "MIN_ORIGIN_PRIMARY_SOURCES", 1,
            ), mock.patch.object(config, "DISCOVERY_REQUIRED_ROLES", frozenset()):
                result = stages.discovery(conn, 1, "question", [])
            self.assertEqual([item["title"] for item in result], ["real"])
            self.assertEqual(result[0]["url"], "https://example.com/real")
        finally:
            stages.llm.call = original_call
            conn.close()

    def test_discovery_discards_login_source_and_requires_origin_primary(self) -> None:
        conn = db.connect(pathlib.Path(self.temp.name) / "source-quality.db")
        original_call = stages.llm.call
        try:
            def fake_call(*_args, **kwargs):
                kwargs["collect_urls"].extend([
                    "https://origin.example/a",
                    "https://archive.example/b",
                    "https://mirror.example/c",
                    "https://login.example/d",
                ])
                return json.dumps({"sources": [
                    {
                        "url": "https://origin.example/a", "title": "a",
                        "publisher": "Origin A", "class": "PRIMARY",
                        "host_role": "ORIGINATING_AUTHORITY",
                        "access_claim": "FULL_TEXT_NO_LOGIN",
                        "published_at": "2026-08-21",
                        "evidence_status": "OBSERVED_CURRENT_RECORD",
                        "evidence_roles": ["CURRENT_SCALE", "MECHANISM"],
                        "answers_why": True,
                        "has_numbers": True, "note": "fixture",
                    },
                    {
                        "url": "https://archive.example/b", "title": "b",
                        "publisher": "Origin B", "class": "PRIMARY",
                        "host_role": "OFFICIAL_ARCHIVE",
                        "access_claim": "FULL_TEXT_NO_LOGIN",
                        "published_at": "2025",
                        "evidence_status": "ENACTED_OR_IN_FORCE",
                        "evidence_roles": ["SECOND_ACT"], "answers_why": True,
                        "has_numbers": False, "note": "fixture",
                    },
                    {
                        "url": "https://mirror.example/c", "title": "c",
                        "publisher": "Origin C", "class": "PRIMARY",
                        "host_role": "MIRROR",
                        "access_claim": "FULL_TEXT_NO_LOGIN",
                        "published_at": "2024", "evidence_status": "UNKNOWN",
                        "evidence_roles": ["BACKGROUND"], "answers_why": False,
                        "has_numbers": False, "note": "fixture",
                    },
                    {
                        "url": "https://login.example/d", "title": "d",
                        "publisher": "Support D", "class": "SUPPORTING",
                        "host_role": "ORIGINATING_AUTHORITY",
                        "access_claim": "LANDING_ONLY_OR_LOGIN",
                        "published_at": "2026-01-01",
                        "evidence_status": "OBSERVED_CURRENT_RECORD",
                        "evidence_roles": ["MECHANISM"], "answers_why": True,
                        "has_numbers": True, "note": "fixture",
                    },
                ]})

            stages.llm.call = fake_call
            result = stages.discovery(conn, 1, "question", [])
            self.assertEqual([source["title"] for source in result], ["a", "b", "c"])
            self.assertEqual(
                sum(
                    source["host_role"] in {
                        "ORIGINATING_AUTHORITY", "OFFICIAL_ARCHIVE"
                    }
                    for source in result if source["class"] == "PRIMARY"
                ),
                2,
            )
        finally:
            stages.llm.call = original_call
            conn.close()

    def test_proposed_record_cannot_satisfy_current_scale(self) -> None:
        conn = db.connect(pathlib.Path(self.temp.name) / "proposed-role.db")
        original_call = stages.llm.call
        try:
            def fake_call(*_args, **kwargs):
                urls = [
                    "https://origin.example/proposal",
                    "https://archive.example/analysis",
                ]
                kwargs["collect_urls"].extend(urls)
                return json.dumps({"sources": [
                    {
                        "url": urls[0], "title": "proposal", "publisher": "A",
                        "class": "PRIMARY", "host_role": "ORIGINATING_AUTHORITY",
                        "access_claim": "FULL_TEXT_NO_LOGIN",
                        "published_at": "2026-08-21",
                        "evidence_status": "PROPOSED_OR_PENDING",
                        "evidence_roles": ["CURRENT_SCALE"],
                        "answers_why": True, "has_numbers": True, "note": "fixture",
                    },
                    {
                        "url": urls[1], "title": "analysis", "publisher": "B",
                        "class": "PRIMARY", "host_role": "OFFICIAL_ARCHIVE",
                        "access_claim": "FULL_TEXT_NO_LOGIN",
                        "published_at": "2025",
                        "evidence_status": "HISTORICAL_ANALYSIS",
                        "evidence_roles": ["MECHANISM", "SECOND_ACT"],
                        "answers_why": True, "has_numbers": True, "note": "fixture",
                    },
                ]})

            stages.llm.call = fake_call
            with self.assertRaisesRegex(ValueError, "CURRENT_SCALE"):
                stages.discovery(conn, 1, "question", [])
        finally:
            stages.llm.call = original_call
            conn.close()

    def test_fetch_persists_requested_final_redirects_and_ips(self) -> None:
        conn = db.connect(pathlib.Path(self.temp.name) / "fetch.db")
        original_get = stages.safe_fetch.get
        original_require = stages.capabilities.require
        requested = "https://example.com/start"
        final = "https://other.example/final"
        html = ("<html><body><article><p>Documented rule and decision. "
                * 80 + "</p></article></body></html>").encode()
        response = safe_fetch.SafeResponse(
            200, {"content-type": "text/html; charset=utf-8"}, html, final,
            (
                safe_fetch.FetchHop(requested, "example.com", (PUBLIC_V4,), 301),
                safe_fetch.FetchHop(final, "other.example", (PUBLIC_V4_ALT,), 200),
            ),
        )
        try:
            stages.safe_fetch.get = lambda *_args, **_kwargs: response
            stages.capabilities.require = lambda *_args, **_kwargs: None
            result = stages.fetch(conn, 1, [{
                "url": requested, "host": "example.com", "class": "PRIMARY",
                "title": "Rule",
            }])
        finally:
            stages.safe_fetch.get = original_get
            stages.capabilities.require = original_require
        self.assertEqual(result[0]["requested_url"], requested)
        self.assertEqual(result[0]["url"], final)
        row = conn.execute(
            "SELECT requested_url, final_url, redirect_chain_json, "
            "resolved_ips_json, fetched_ok FROM sources").fetchone()
        self.assertEqual(row["requested_url"], requested)
        self.assertEqual(row["final_url"], final)
        self.assertEqual(json.loads(row["redirect_chain_json"]), [requested, final])
        self.assertEqual(json.loads(row["resolved_ips_json"])["other.example"],
                         [PUBLIC_V4_ALT])
        self.assertEqual(row["fetched_ok"], 1)
        conn.close()

    def test_research_browser_fallback_is_fail_closed(self) -> None:
        result = stages._dobierz_przegladarka(
            None, 1, [{"url": "https://example.com/a"}], [])
        self.assertEqual(result, [])
        source = pathlib.Path(browser.__file__).read_text(encoding="utf-8")
        body = source[source.index("def read_pages"):source.index(
            "def restackuj_w_kanale")]
        executable = body.split('"""')[-1]
        self.assertNotIn("page.goto", executable)
        self.assertIn("raise RuntimeError", executable)

    def test_pdf_parser_caps_stream_and_text_then_restores_global(self) -> None:
        original_reader = pypdf.PdfReader
        original_limit = pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH
        seen_limits = []

        class Page:
            def extract_text(self):
                return "x" * 80

        class Reader:
            def __init__(self, _stream):
                seen_limits.append(pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH)
                self.pages = [Page(), Page(), Page()]

        try:
            pypdf.PdfReader = Reader
            text = stages._tekst_z_pdf(b"fixture", max_stron=2, max_znakow=100)
            self.assertEqual(len(text), 100)
            self.assertEqual(
                seen_limits,
                [min(original_limit,
                     config.FETCH_MAX_PDF_DECOMPRESSED_STREAM_BYTES)],
            )
        finally:
            pypdf.PdfReader = original_reader
        self.assertEqual(pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH, original_limit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
