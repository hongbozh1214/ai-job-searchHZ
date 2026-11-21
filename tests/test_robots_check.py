"""Offline tests for tools/robots_check.py.

No network: every case exercises the parser against literal robots.txt bodies,
matching the repo's CI policy of making no live portal requests.

The cases marked FAIL-OPEN REGRESSION are the ones Python's own
urllib.robotparser gets wrong. They are pinned here because getting them wrong
means the browser-header retry runs against a site that said no, which is the
exact boundary this tool exists to hold.
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from robots_check import allowed, has_undecodable_rule, is_robots_body  # noqa: E402


# Real body served by privatebank.barclays.com: blank lines sit between the
# User-agent line and its rules. Python's robotparser treats those as record
# separators and drops every rule, so /cs/ reads as allowed.
BARCLAYS = "User-agent: *\n\n\nAllow: /\n\nDisallow: /cs/\n\nSitemap: https://x/sitemap.xml\n"

# jobup.ch: the case a community fork was asked to ship opt-in.
JOBUP = "User-agent: *\nDisallow: /api/\n"


class TestPathRules(unittest.TestCase):
    def test_blank_lines_inside_record_do_not_end_it(self):
        """FAIL-OPEN REGRESSION: /cs/ is disallowed despite the blank lines."""
        self.assertFalse(allowed(BARCLAYS, "*", "/cs/"))

    def test_allowed_path_on_same_site_still_allowed(self):
        self.assertTrue(allowed(BARCLAYS, "*", "/careers/"))

    def test_longest_match_wins_over_rule_order(self):
        """FAIL-OPEN REGRESSION: 'Allow: /' precedes 'Disallow: /cs/' in the
        file; specificity must win, not position."""
        body = "User-agent: *\nAllow: /\nDisallow: /cs/\n"
        self.assertFalse(allowed(body, "*", "/cs/deep/page"))

    def test_longest_match_can_unblock(self):
        body = "User-agent: *\nDisallow: /\nAllow: /jobs/\n"
        self.assertTrue(allowed(body, "*", "/jobs/x"))
        self.assertFalse(allowed(body, "*", "/other"))

    def test_equal_specificity_tie_goes_to_disallow(self):
        """Cautious tie-break: Google resolves ties to Allow, we do not."""
        self.assertFalse(allowed("User-agent: *\nDisallow: /a\nAllow: /a\n", "*", "/a"))

    def test_equal_specificity_tie_goes_to_disallow_when_allow_listed_first(self):
        """The only ordering that exercises the tie-break clause: with Allow
        first, deleting the clause makes the first rule at a given length win
        and Allow would leak through. The Disallow-first sibling above cannot
        detect that mutation (review finding F21, 2026-08-19)."""
        self.assertFalse(allowed("User-agent: *\nAllow: /a\nDisallow: /a\n", "*", "/a"))

    def test_api_block_and_sibling_path(self):
        self.assertFalse(allowed(JOBUP, "*", "/api/v1/public/search"))
        self.assertTrue(allowed(JOBUP, "*", "/en/jobs/"))

    def test_wildcard_and_end_anchor(self):
        body = "User-agent: *\nDisallow: /*.pdf$\n"
        self.assertFalse(allowed(body, "*", "/files/cv.pdf"))
        self.assertTrue(allowed(body, "*", "/files/cv.pdf.html"))

    def test_empty_disallow_means_allow_everything(self):
        self.assertTrue(allowed("User-agent: *\nDisallow:\n", "*", "/anything"))

    def test_empty_or_ruleless_robots_allows(self):
        self.assertTrue(allowed("", "*", "/x"))
        self.assertTrue(allowed("# just a comment\n", "*", "/x"))

    def test_comments_are_stripped(self):
        self.assertFalse(allowed("User-agent: *\nDisallow: /x  # nope\n", "*", "/x"))


class TestAgentSelection(unittest.TestCase):
    def test_named_claude_user_opt_out_is_honored(self):
        body = "User-agent: Claude-User\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        self.assertFalse(allowed(body, "Claude-User", "/a"))
        self.assertTrue(allowed(body, "*", "/a"))

    def test_agent_match_is_case_insensitive(self):
        body = "User-agent: CLAUDE-USER\nDisallow: /x\n"
        self.assertFalse(allowed(body, "claude-user", "/x"))

    def test_falls_back_to_star_when_agent_absent(self):
        self.assertFalse(allowed(JOBUP, "Claude-User", "/api/v1"))

    def test_multiple_agents_share_one_ruleset(self):
        body = "User-agent: A\nUser-agent: Claude-User\nDisallow: /z\n"
        self.assertFalse(allowed(body, "Claude-User", "/z"))
        self.assertFalse(allowed(body, "A", "/z"))

    def test_gate_honors_a_runtime_specific_user_agent(self):
        import robots_check

        body = "User-agent: OpenClaw-Fetch\nDisallow: /private\n"
        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: (body, 200)
        try:
            rc, msg = robots_check.gate(
                "https://example.test/private/job",
                agent="OpenClaw-Fetch",
            )
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 1)
        self.assertIn("OpenClaw-Fetch", msg)


class TestCli(unittest.TestCase):
    def test_module_is_importable_and_cli_exists(self):
        """The doc calls this by path; make sure that entry point stays valid."""
        script = REPO_ROOT / "tools" / "robots_check.py"
        self.assertTrue(script.is_file())
        out = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, timeout=30
        )
        # No URL argument: must fail loudly rather than defaulting to "allowed".
        self.assertNotEqual(out.returncode, 0)


class TestSoftTwoHundred(unittest.TestCase):
    """A 200 whose body is not a robots.txt used to grant permission.

    Found by adversarial review, not inspection. A misconfigured host answering
    /robots.txt with an HTML error page at status 200 parses to zero rules, and
    zero rules read as "allowed" - so the browser retry ran on permission that
    was never given. FAIL-OPEN REGRESSION.
    """

    def test_html_error_page_is_not_a_robots_file(self):
        self.assertFalse(is_robots_body("<html><body>404 Not Found</body></html>"))

    def test_json_error_body_is_not_a_robots_file(self):
        self.assertFalse(is_robots_body('{"error":"not found"}'))

    def test_soft_200_is_unconfirmed_not_allowed(self):
        import robots_check

        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: ("<html>404</html>", 200)
        try:
            rc, msg = robots_check.gate("https://x.example/jobs")
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 1)
        self.assertIn("not a robots.txt", msg)

    def test_gate_reads_policy_as_browser_when_honest_request_is_refused(self):
        """09-web-research.md's Barclays-class recovery: the policy file itself
        returns 403 to Claude-User and 200 to a browser, and the checker must
        then read it as a browser and obey it strictly. This is gate()'s UA
        fallback loop, previously untested despite the doc's coverage claim
        (review finding F30, 2026-08-19)."""
        import robots_check

        original = robots_check._fetch

        def waf(url, ua):
            if ua == robots_check.BROWSER:
                return ("User-agent: *\nAllow: /\n", 200)
            return ("<html>403 Forbidden</html>", 403)

        robots_check._fetch = waf
        try:
            rc, msg = robots_check.gate("https://waf.example/jobs")
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 0)
        self.assertIn("ALLOWED", msg)

    def test_gate_obeys_a_browser_fetched_policy_strictly(self):
        """The fallback must not fail open: a policy readable only as a browser
        still disallows what it disallows."""
        import robots_check

        original = robots_check._fetch

        def waf(url, ua):
            if ua == robots_check.BROWSER:
                return ("User-agent: *\nDisallow: /jobs\n", 200)
            return ("<html>403 Forbidden</html>", 403)

        robots_check._fetch = waf
        try:
            rc, msg = robots_check.gate("https://waf.example/jobs")
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 1)
        self.assertIn("DISALLOWED", msg)

    def test_a_genuinely_empty_robots_is_still_allow_all(self):
        """RFC 9309: an empty file permits everything. Do not over-correct."""
        self.assertTrue(is_robots_body(""))
        self.assertTrue(is_robots_body("\n\n   \n"))

    def test_a_real_policy_is_recognised(self):
        self.assertTrue(is_robots_body(BARCLAYS))
        self.assertTrue(is_robots_body(JOBUP))

    def test_sitemap_only_file_counts(self):
        self.assertTrue(is_robots_body("Sitemap: https://x.example/sitemap.xml\n"))


class TestPercentEncodedRules(unittest.TestCase):
    """Rule patterns are percent-decoded to match the decoded request path.

    FAIL-OPEN REGRESSION: without this, a site that percent-encodes its own
    Disallow patterns has them silently skipped.
    """

    def test_encoded_space_in_disallow_now_matches(self):
        self.assertFalse(allowed("User-agent: *\nDisallow: /foo%20bar\n", "*", "/foo bar"))

    def test_encoded_rule_does_not_overmatch(self):
        self.assertTrue(allowed("User-agent: *\nDisallow: /foo%20bar\n", "*", "/foobar"))

    def test_plain_rules_are_unaffected(self):
        self.assertFalse(allowed(JOBUP, "*", "/api/x"))
        self.assertTrue(allowed(JOBUP, "*", "/en/jobs/x"))



class TestArgumentHardening(unittest.TestCase):
    """A URL can never be read by curl as an option.

    gate() rebuilds the target as scheme://host/robots.txt, so the gate path was
    never exposed; this pins the "--" terminator for direct _fetch callers and
    confirms a dash-leading argument fails closed end to end.
    """

    def test_curl_argv_ends_with_a_double_dash_before_the_url(self):
        import inspect

        import robots_check

        src = inspect.getsource(robots_check._fetch)
        self.assertIn("'--', url", src)

    def test_a_dash_leading_argument_fails_closed(self):
        script = REPO_ROOT / "tools" / "robots_check.py"
        out = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(out.returncode, 0)
        self.assertNotIn("Usage: curl", out.stdout)

    def test_gate_never_passes_the_caller_url_through_to_curl(self):
        """The robots target is rebuilt from scheme+host, never the raw input."""
        import robots_check

        seen = []

        original = robots_check._fetch

        def spy(url, ua):
            seen.append(url)
            return "User-agent: *\nAllow: /\n", 200

        robots_check._fetch = spy
        try:
            robots_check.gate("https://x.example/-o/evil?q=1")
        finally:
            robots_check._fetch = original
        self.assertEqual(seen[0], "https://x.example/robots.txt")



class TestStrictMode(unittest.TestCase):
    def test_strict_single_request_and_no_redirect_flags(self):
        from unittest.mock import patch
        import robots_check
        result = subprocess.CompletedProcess([], 0, stdout="User-agent: *\nAllow: /\n\n200", stderr="")
        with patch.object(robots_check.subprocess, "run", return_value=result) as run:
            rc, _ = robots_check.gate("https://example.test/jobs", agent="company-pages-search-skill", strict=True)
        self.assertEqual(rc, 0)
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertEqual(args[1], '-q')
        self.assertNotIn("-L", args)
        self.assertNotIn("--location", args)
        self.assertNotIn("--max-redirs", args)
        self.assertEqual(args[args.index("-A") + 1], "company-pages-search-skill")
        self.assertEqual(args[-1], "https://example.test/robots.txt")
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")
        self.assertEqual(args[args.index("--proto") + 1], "=http,https")
        self.assertEqual(args[args.index("--proto-redir") + 1], "=http,https")

    def test_imported_parser_fixes_keep_strict_decisions_and_single_request(self):
        from unittest.mock import patch
        import robots_check
        for body, url, verdict in [
            ("\ufeffUser-agent: *\nDisallow: /\n", "https://example.test/jobs", "DISALLOWED"),
            ("User-agent: *\nDisallow: /\ufffd\n", "https://example.test/jobs", "UNCONFIRMED"),
            ("User-agent: *\nDisallow: /search?q=machine%20learning\n", "https://example.test/search?q=machine%20learning", "DISALLOWED"),
        ]:
            with self.subTest(verdict=verdict, url=url), patch.object(robots_check, "_fetch", return_value=(body, 200)) as fetch:
                rc, msg = robots_check.gate(url, strict=True)
                self.assertEqual(rc, 1)
                self.assertTrue(msg.startswith(verdict), msg)
                fetch.assert_called_once_with("https://example.test/robots.txt", "Claude-User", strict=True)

    def test_strict_denies_error_redirect_missing_and_invalid_policy_without_retry(self):
        from unittest.mock import patch
        import robots_check
        for code, body in [(301, ""), (302, ""), (403, ""), (404, ""), (429, ""), (500, ""), (200, "<html>challenge</html>")]:
            with self.subTest(code=code), patch.object(robots_check, "_fetch", return_value=(body, code)) as fetch:
                rc, _ = robots_check.gate("https://example.test/jobs", strict=True)
                self.assertEqual(rc, 1)
                fetch.assert_called_once_with("https://example.test/robots.txt", "Claude-User", strict=True)
        with patch.object(robots_check, "_fetch", side_effect=TimeoutError) as fetch:
            self.assertEqual(robots_check.gate("https://example.test/jobs", strict=True)[0], 1)
            self.assertEqual(fetch.call_count, 1)

    def test_strict_obeys_robots_deny(self):
        from unittest.mock import patch
        import robots_check
        with patch.object(robots_check, "_fetch", return_value=("User-agent: *\nDisallow: /jobs\n", 200)) as fetch:
            self.assertEqual(robots_check.gate("https://example.test/jobs", strict=True)[0], 1)
            self.assertEqual(fetch.call_count, 1)

    def test_default_still_falls_back_and_follows_redirects(self):
        from unittest.mock import patch
        import robots_check
        responses = [subprocess.CompletedProcess([], 0, stdout="denied\n403", stderr=""), subprocess.CompletedProcess([], 0, stdout="User-agent: *\nAllow: /\n\n200", stderr="")]
        with patch.object(robots_check.subprocess, "run", side_effect=responses) as run:
            self.assertEqual(robots_check.gate("https://example.test/jobs")[0], 0)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertIn("-L", call.args[0])


class TestByteOrderMark(unittest.TestCase):
    """One leading UTF-8 byte-order mark is skipped before parsing.

    FAIL-OPEN REGRESSION: a robots.txt saved with a BOM decodes to a body that
    starts with U+FEFF, so its first field was U+FEFF + "user-agent", which is
    not "user-agent". A leading "User-agent: *" went unseen, every rule in its
    group was dropped for want of an agent, and "Disallow: /" read as
    allow-all. Google's reference parser skips the BOM; Python's robotparser
    does not.
    """

    BODY = "\ufeffUser-agent: *\nDisallow: /\n"

    def test_bom_does_not_hide_the_first_group(self):
        self.assertFalse(allowed(self.BODY, "*", "/x"))
        self.assertFalse(allowed(self.BODY, "Claude-User", "/x"))

    def test_gate_obeys_a_policy_saved_with_a_bom(self):
        import robots_check

        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: (self.BODY, 200)
        try:
            rc, msg = robots_check.gate("https://bom.example/jobs")
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 1)
        self.assertIn("DISALLOWED", msg)

    def test_is_robots_body_skips_the_bom_too(self):
        """A lone directive behind a BOM read as a soft 200 (fail-closed, but
        wrong). A BOM-only file is an empty file: allow-all, as RFC 9309 says."""
        self.assertTrue(is_robots_body("\ufeffSitemap: https://x.example/sitemap.xml\n"))
        self.assertTrue(is_robots_body("\ufeff"))

class TestUndecodableRules(unittest.TestCase):
    """A User-agent, Allow or Disallow line holding U+FFFD is unreadable.

    FAIL-OPEN REGRESSION: read as the UTF-8 that RFC 9309 requires, with bad
    bytes replaced, a non-conformant robots.txt saved in cp1254 turns
    "Disallow: /şirket/" into a pattern holding U+FFFD. It can never match, so
    the rule was silently skipped and the path read as allowed. The gate now
    leaves permission unconfirmed instead. U+FFFD in a comment or an unrelated
    line decides nothing and must stay harmless.
    """

    @staticmethod
    def _legacy(text):
        """`text` saved in cp1254, then read as UTF-8 with bad bytes replaced."""
        return text.encode("cp1254").decode("utf-8", "replace")

    def _gate(self, body, url):
        import robots_check

        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: (body, 200)
        try:
            return robots_check.gate(url)
        finally:
            robots_check._fetch = original

    def test_undecodable_disallow_is_unconfirmed_not_allowed(self):
        body = self._legacy("User-agent: *\nDisallow: /şirket/\n")
        self.assertIn("\ufffd", body)
        rc, msg = self._gate(body, "https://legacy.example/şirket/x")
        self.assertEqual(rc, 1, msg)
        self.assertIn("UNCONFIRMED", msg)
        self.assertIn("not valid UTF-8", msg)

    def test_undecodable_star_agent_is_unconfirmed(self):
        """A trailing 0xA0 is a no-break space in cp1254, which strip() removes,
        but U+FFFD in UTF-8, which it does not: "*" became another agent and
        the group's Disallow stopped applying."""
        body = self._legacy("User-agent: *\xa0\nDisallow: /\n")
        rc, msg = self._gate(body, "https://legacy.example/jobs")
        self.assertEqual(rc, 1, msg)
        self.assertIn("UNCONFIRMED", msg)

    def test_undecodable_byte_before_the_field_is_unconfirmed(self):
        """A 0xA0 indent garbled the field name, so the Disallow went unseen."""
        body = self._legacy("User-agent: *\n\xa0Disallow: /jobs\n")
        rc, msg = self._gate(body, "https://legacy.example/jobs")
        self.assertEqual(rc, 1, msg)
        self.assertIn("UNCONFIRMED", msg)

    def test_every_rule_line_is_checked(self):
        """User-agent, Allow and Disallow alike, and a first line behind a BOM:
        _groups skips the BOM, so the check must too or it misses that line."""
        for body in (
            self._legacy("User-agent: Bot\xa0\n"),
            self._legacy("Allow: /ş/\n"),
            self._legacy("Disallow: /ş/\n"),
            "\ufeff" + self._legacy("User-agent: *\xa0\nDisallow: /\n"),
        ):
            with self.subTest(body=body):
                self.assertTrue(has_undecodable_rule(body))

    def test_fffd_in_a_comment_or_an_unrelated_line_is_harmless(self):
        body = self._legacy(
            "# Şirket politikası\n"
            "User-agent: *\n"
            "Disallow: /api/  # özel\n"
            "Sitemap: https://legacy.example/şirket.xml\n"
            "Açıklama: iş ilanları\n"
        )
        # Every line but the User-agent holds U+FFFD, so the case is not vacuous.
        clean = [line for line in body.splitlines() if "\ufffd" not in line]
        self.assertEqual(clean, ["User-agent: *"])
        self.assertFalse(has_undecodable_rule(body))
        rc, msg = self._gate(body, "https://legacy.example/jobs")
        self.assertEqual(rc, 0, msg)
        rc, msg = self._gate(body, "https://legacy.example/api/x")
        self.assertEqual(rc, 1, msg)
        self.assertIn("DISALLOWED", msg)

    def test_valid_utf8_non_ascii_rules_are_still_obeyed(self):
        """Real UTF-8 never decodes to U+FFFD. The first rule is tr.indeed.com's."""
        body = "User-agent: *\nDisallow: /職涯貼士/\nDisallow: /şirket/\n"
        self.assertFalse(has_undecodable_rule(body))
        for path in ("/職涯貼士/x", "/şirket/x"):
            rc, msg = self._gate(body, "https://tr.indeed.example" + path)
            self.assertEqual(rc, 1, msg)
            self.assertIn("DISALLOWED", msg)
        rc, msg = self._gate(body, "https://tr.indeed.example/cmp/x/reviews")
        self.assertEqual(rc, 0, msg)

class TestQueryAndAnchorRules(unittest.TestCase):
    def test_dollar_sign_mid_pattern_is_literal_not_end_anchor(self):
        body = "User-agent: *\nDisallow: /tag/$var\n"
        self.assertFalse(allowed(body, "*", "/tag/$var"))
        self.assertFalse(allowed(body, "*", "/tag/$var/sub"))

    def test_percent_encoded_query_string_matches_rule_in_gate(self):
        import robots_check

        body = "User-agent: *\nDisallow: /search?q=machine%20learning\n"
        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: (body, 200)
        try:
            rc, msg = robots_check.gate("https://example.com/search?q=machine%20learning")
        finally:
            robots_check._fetch = original
        self.assertEqual(rc, 1, msg)
        self.assertIn("DISALLOWED", msg)

class TestBoundedWildcardRules(unittest.TestCase):
    def test_repeated_wildcards_do_not_catastrophically_backtrack(self):
        # GHSA-xhqf-8q8x-4jwm: every '*' became a regex '.*', so a rule with
        # repeated wildcard segments that does not match took exponential time
        # in Python's backtracking engine (16 segments: minutes). The matcher
        # must run in O(len(pattern) * len(path)) whatever the rule says.
        import time

        pat = "/" + "*a" * 13 + "*b$"
        body = f"User-agent: *\nDisallow: {pat}\n"
        path = "/" + "a" * 28 + "X"
        start = time.perf_counter()
        res = allowed(body, "*", path)
        elapsed = time.perf_counter() - start
        self.assertTrue(res)
        self.assertLess(elapsed, 0.5, f"_match took {elapsed:.2f}s (catastrophic backtracking)")

    def test_consecutive_wildcards_match_identically_to_single_wildcard(self):
        body = "User-agent: *\nDisallow: /docs/*******.pdf$\n"
        self.assertFalse(allowed(body, "*", "/docs/cv.pdf"))
        self.assertFalse(allowed(body, "*", "/docs/sub/folder/cv.pdf"))
        self.assertTrue(allowed(body, "*", "/docs/sub/folder/cv.html"))

    def test_wildcard_semantics_survive_the_matcher_change(self):
        # Pinned against the regex matcher's answers: prefix match without '$',
        # full match with it, a wildcard spanning slashes and the empty string,
        # and a trailing wildcard before the anchor.
        body = (
            "User-agent: *\n"
            "Disallow: /a*b\n"
            "Disallow: /x/*/y$\n"
            "Disallow: /end*$\n"
        )
        self.assertFalse(allowed(body, "*", "/ab"))
        self.assertFalse(allowed(body, "*", "/a/long/path/b/and-more"))
        self.assertTrue(allowed(body, "*", "/a"))
        self.assertFalse(allowed(body, "*", "/x/anything/at/all/y"))
        self.assertTrue(allowed(body, "*", "/x/anything/y/more"))
        self.assertFalse(allowed(body, "*", "/end"))
        self.assertFalse(allowed(body, "*", "/ending/here"))
        self.assertTrue(allowed(body, "*", "/en"))

class TestSchemeHardening(unittest.TestCase):
    """GHSA-h8vc-753p-wpmh: only http(s) reaches curl, on the first hop and on
    every redirect.

    gate() rebuilt the target as scheme://host/robots.txt but never checked the
    scheme, so a direct call with file:, gopher: or ftp: handed that scheme to
    curl, and curl -L was free to follow a redirect to any protocol it supports.
    """

    def _gate_without_curl(self, url):
        # Record rather than fail inside the spy: gate() swallows every
        # exception from _fetch into an UNCONFIRMED verdict, which would pass.
        import robots_check

        fetched = []
        original = robots_check._fetch
        robots_check._fetch = lambda url, ua: fetched.append(url) or ("", 404)
        try:
            result = robots_check.gate(url)
        finally:
            robots_check._fetch = original
        self.assertEqual(fetched, [], f"curl was asked for {fetched}")
        return result

    def test_non_http_scheme_is_unconfirmed_without_a_fetch(self):
        for url in ("file:///etc/passwd", "gopher://127.0.0.1:6379/_", "ftp://x.example/robots.txt", "x.example/path"):
            with self.subTest(url=url):
                rc, msg = self._gate_without_curl(url)
                self.assertEqual(rc, 1)
                self.assertTrue(msg.startswith("UNCONFIRMED"), msg)
                self.assertIn("scheme", msg)

    def test_missing_host_is_unconfirmed_without_a_fetch(self):
        rc, msg = self._gate_without_curl("http:///robots.txt")
        self.assertEqual(rc, 1)
        self.assertTrue(msg.startswith("UNCONFIRMED"), msg)

    def test_curl_is_pinned_to_http_and_https_on_every_hop(self):
        import robots_check

        seen = []

        class Done:
            returncode, stdout, stderr = 0, "\n404", ""

        def fake_run(argv, **kwargs):
            seen.append(argv)
            return Done()

        original = robots_check.subprocess.run
        robots_check.subprocess.run = fake_run
        try:
            body, code = robots_check._fetch("https://x.example/robots.txt", "Claude-User")
        finally:
            robots_check.subprocess.run = original
        self.assertEqual(code, 404)
        argv = seen[0]
        self.assertIn("--proto", argv)
        self.assertEqual(argv[argv.index("--proto") + 1], "=http,https")
        self.assertIn("--proto-redir", argv)
        self.assertEqual(argv[argv.index("--proto-redir") + 1], "=http,https")
        self.assertLess(argv.index("--proto-redir"), argv.index("--"))




if __name__ == "__main__":
    unittest.main()
