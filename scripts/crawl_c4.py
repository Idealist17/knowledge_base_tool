#!/usr/bin/env python3
"""
Build a local Code4rena dataset for Learn KG.

The output layout matches the `learnkg learn-c4 --c4-dir ...` input format:

    out_train/
      audits/<id>.json
      reports/<id>.md
      contracts/<id>/
      manifest.json
      failures.jsonl

The crawler intentionally uses only the Python standard library so it can run
in a fresh checkout without extra package installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://code4rena.com"
REPORTS_URL = f"{BASE_URL}/reports"
USER_AGENT = "learn-kg-c4-crawler/1.0"
GITHUB_REPO_RE = re.compile(r"^https://github\.com/[^/\s\"'>]+/[^/\s\"'>#?]+/?$")


@dataclass(frozen=True)
class ReportEntry:
    contest_id: int
    slug: str
    sponsor: str
    title: str
    date: str | None
    start_time: str | None
    end_time: str | None
    report_url: str
    findings_url: str | None
    alt_url: str | None


@dataclass
class SuccessRecord:
    id: int
    slug: str
    title: str
    sponsor: str
    year: int
    report_url: str
    source_repo: str
    audit_path: str
    report_path: str
    contracts_path: str
    solidity_files: int
    findings_url: str | None
    start_time: str | None
    end_time: str | None


@dataclass
class FailureRecord:
    slug: str
    report_url: str
    reason: str
    stage: str


class Fetcher:
    def __init__(self, retry: int, github_token: str | None):
        self.retry = max(retry, 1)
        self.github_token = github_token

    def get_text(self, url: str) -> str:
        headers = {"User-Agent": USER_AGENT}
        if self.github_token and self._is_github_api_or_raw(url):
            headers["Authorization"] = f"Bearer {self.github_token}"

        last_error: Exception | None = None
        for attempt in range(1, self.retry + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=45) as resp:
                    raw = resp.read()
                    charset = resp.headers.get_content_charset() or "utf-8"
                    return raw.decode(charset, "replace")
            except (urllib.error.URLError, TimeoutError) as err:
                last_error = err
                if attempt < self.retry:
                    time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"failed to fetch {url}: {last_error}")

    @staticmethod
    def _is_github_api_or_raw(url: str) -> bool:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host in {"api.github.com", "raw.githubusercontent.com"}


class MarkdownConverter(HTMLParser):
    """Small HTML-to-Markdown converter focused on Code4rena report pages."""

    BLOCK_TAGS = {"p", "div", "section", "article", "main", "blockquote"}
    LIST_TAGS = {"ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.href_stack: list[str | None] = []
        self.skip_stack: list[str] = []
        self.list_stack: list[str] = []
        self.in_pre = False
        self.in_code = False
        self.heading_level: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "svg", "nav", "footer", "header", "button"}:
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return

        if re.fullmatch(r"h[1-6]", tag):
            self._newline(2)
            self.heading_level = int(tag[1])
            self.out.append("#" * self.heading_level + " ")
        elif tag in self.BLOCK_TAGS:
            self._newline(2)
        elif tag in self.LIST_TAGS:
            self.list_stack.append(tag)
            self._newline(1)
        elif tag == "li":
            self._newline(1)
            self.out.append("- ")
        elif tag == "br":
            self.out.append("\n")
        elif tag == "a":
            self.href_stack.append(attrs_dict.get("href"))
        elif tag == "pre":
            self._newline(2)
            self.out.append("```")
            self._newline(1)
            self.in_pre = True
        elif tag == "code" and not self.in_pre:
            self.out.append("`")
            self.in_code = True
        elif tag in {"strong", "b"}:
            self.out.append("**")
        elif tag in {"em", "i"}:
            self.out.append("_")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_stack:
            if self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return

        if re.fullmatch(r"h[1-6]", tag):
            self.heading_level = None
            self._newline(2)
        elif tag in self.BLOCK_TAGS:
            self._newline(2)
        elif tag in self.LIST_TAGS:
            if self.list_stack:
                self.list_stack.pop()
            self._newline(2)
        elif tag == "a":
            href = self.href_stack.pop() if self.href_stack else None
            if href:
                self.out.append(f" ({href})")
        elif tag == "pre":
            self._newline(1)
            self.out.append("```")
            self._newline(2)
            self.in_pre = False
        elif tag == "code" and self.in_code:
            self.out.append("`")
            self.in_code = False
        elif tag in {"strong", "b"}:
            self.out.append("**")
        elif tag in {"em", "i"}:
            self.out.append("_")

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        if self.in_pre:
            self.out.append(data)
            return
        text = data if self.in_code else re.sub(r"\s+", " ", data)
        if text.strip():
            self.out.append(text)

    def markdown(self) -> str:
        text = "".join(self.out)
        text = html.unescape(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r"^\s+", "", text)
        return text.strip() + "\n"

    def _newline(self, count: int) -> None:
        current = "".join(self.out[-3:])
        existing = len(current) - len(current.rstrip("\n"))
        if existing < count:
            self.out.append("\n" * (count - existing))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl Code4rena reports and source repositories into a Learn KG c4 dataset."
    )
    parser.add_argument("--years", required=True, help="Comma-separated years, e.g. 2024,2025")
    parser.add_argument("--out", default="out_train", type=Path, help="Output dataset directory")
    parser.add_argument("--concurrency", default=4, type=int, help="Concurrent report workers")
    parser.add_argument("--retry", default=3, type=int, help="HTTP retry count")
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip entries with audit/report/contracts already present",
    )
    parser.add_argument(
        "--include-failures",
        action="store_true",
        help="Write failures.jsonl with failed entries",
    )
    return parser.parse_args(argv)


def parse_years(raw: str) -> set[int]:
    years: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not re.fullmatch(r"\d{4}", item):
            raise SystemExit(f"invalid --years item: {item!r}")
        years.add(int(item))
    return years


def stable_contest_id(slug: str, used: set[int]) -> int:
    salt = ""
    while True:
        digest = hashlib.sha256((slug + salt).encode()).hexdigest()
        value = int(digest[:8], 16)
        if value not in used:
            return value
        salt += "x"


def discover_reports(fetcher: Fetcher, years: set[int]) -> list[ReportEntry]:
    page = fetcher.get_text(REPORTS_URL)
    decoded = page.replace('\\"', '"').replace("\\n", "\n")

    contest_times: dict[str, dict[str, Any]] = {}
    for record_id, body in re.findall(r"([0-9a-z]+):\{([^{}]*\"start_time\"[^{}]*)\}", decoded):
        obj = _json_obj_from_body(body)
        if obj:
            contest_times[record_id] = obj

    entries: list[ReportEntry] = []
    used_ids: set[int] = set()
    for _, body in re.findall(r"([0-9a-z]+):\{([^{}]*\"slug\"[^{}]*)\}", decoded):
        obj = _json_obj_from_body(body)
        if not obj or not obj.get("slug"):
            continue

        slug = str(obj["slug"])
        year = _entry_year(obj)
        if year not in years:
            continue

        raw_id = obj.get("contest")
        contest_id = raw_id if isinstance(raw_id, int) else stable_contest_id(slug, used_ids)
        if contest_id in used_ids:
            contest_id = stable_contest_id(slug, used_ids)
        used_ids.add(contest_id)

        contest_ref = str(obj.get("contest_data") or "").removeprefix("$")
        times = contest_times.get(contest_ref, {})
        entries.append(
            ReportEntry(
                contest_id=contest_id,
                slug=slug,
                sponsor=str(obj.get("sponsor") or obj.get("title") or slug),
                title=str(obj.get("title") or obj.get("sponsor") or slug),
                date=str(obj["date"]) if obj.get("date") else None,
                start_time=times.get("start_time"),
                end_time=times.get("end_time"),
                report_url=f"{BASE_URL}/reports/{slug}",
                findings_url=obj.get("findings"),
                alt_url=obj.get("alt_url"),
            )
        )

    # Code4rena currently serializes report data more than once in the page.
    deduped = {entry.slug: entry for entry in entries}
    return sorted(deduped.values(), key=lambda e: (e.date or "", e.slug), reverse=True)


def _json_obj_from_body(body: str) -> dict[str, Any] | None:
    try:
        return json.loads("{" + body + "}")
    except json.JSONDecodeError:
        return None


def _entry_year(obj: dict[str, Any]) -> int:
    for key in ("date", "slug"):
        value = str(obj.get(key) or "")
        match = re.search(r"(20\d{2})", value)
        if match:
            return int(match.group(1))
    return 0


def process_entry(entry: ReportEntry, out: Path, fetcher: Fetcher, skip_existing: bool) -> SuccessRecord:
    audit_path = out / "audits" / f"{entry.contest_id}.json"
    report_path = out / "reports" / f"{entry.contest_id}.md"
    contracts_path = out / "contracts" / str(entry.contest_id)

    if skip_existing and _entry_complete(audit_path, report_path, contracts_path):
        source_repo = _source_repo_from_manifest(out, entry.contest_id) or ""
        return _success_record(entry, source_repo, audit_path, report_path, contracts_path)

    report_html = fetcher.get_text(entry.report_url)
    source_repo = find_source_repo(report_html, entry.slug)
    if not source_repo:
        raise RuntimeError("source GitHub repository not found in report Scope section")

    report_md = fetch_report_markdown(fetcher, entry, report_html)
    if not report_md.strip():
        raise RuntimeError("empty report markdown")

    with tempfile.TemporaryDirectory(prefix=f"c4-{entry.slug}-") as tmp_raw:
        tmp = Path(tmp_raw)
        tmp_audit = tmp / "audit.json"
        tmp_report = tmp / "report.md"
        tmp_contracts = tmp / "contracts"
        tmp_audit.write_text(json.dumps(_audit_json(entry), ensure_ascii=False, indent=2) + "\n")
        tmp_report.write_text(report_md, encoding="utf-8")
        clone_repo(source_repo, tmp_contracts)
        sol_count = count_solidity_files(tmp_contracts)
        if sol_count == 0:
            raise RuntimeError(f"no .sol files found in cloned repository {source_repo}")

        audit_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        contracts_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(tmp_audit), audit_path)
        shutil.move(str(tmp_report), report_path)
        if contracts_path.exists():
            shutil.rmtree(contracts_path)
        shutil.move(str(tmp_contracts), contracts_path)

    return _success_record(entry, source_repo, audit_path, report_path, contracts_path)


def _entry_complete(audit_path: Path, report_path: Path, contracts_path: Path) -> bool:
    return (
        audit_path.is_file()
        and report_path.is_file()
        and report_path.stat().st_size > 0
        and contracts_path.is_dir()
        and count_solidity_files(contracts_path) > 0
    )


def _source_repo_from_manifest(out: Path, contest_id: int) -> str | None:
    manifest = out / "manifest.json"
    if not manifest.is_file():
        return None
    with contextlib.suppress(Exception):
        data = json.loads(manifest.read_text())
        for entry in data.get("projects", []):
            if entry.get("id") == contest_id:
                return entry.get("source_repo")
    return None


def _success_record(
    entry: ReportEntry, source_repo: str, audit_path: Path, report_path: Path, contracts_path: Path
) -> SuccessRecord:
    return SuccessRecord(
        id=entry.contest_id,
        slug=entry.slug,
        title=entry.title,
        sponsor=entry.sponsor,
        year=_year_from_entry(entry),
        report_url=entry.report_url,
        source_repo=source_repo,
        audit_path=str(audit_path),
        report_path=str(report_path),
        contracts_path=str(contracts_path),
        solidity_files=count_solidity_files(contracts_path),
        findings_url=entry.findings_url,
        start_time=entry.start_time,
        end_time=entry.end_time,
    )


def _year_from_entry(entry: ReportEntry) -> int:
    for value in (entry.date, entry.slug):
        if value:
            match = re.search(r"(20\d{2})", value)
            if match:
                return int(match.group(1))
    return 0


def _audit_json(entry: ReportEntry) -> dict[str, Any]:
    return {
        "contestId": entry.contest_id,
        "title": entry.title,
        "slug": entry.slug,
        "startTime": entry.start_time,
        "endTime": entry.end_time,
        "details": entry.report_url,
    }


def fetch_report_markdown(fetcher: Fetcher, entry: ReportEntry, report_html: str) -> str:
    raw_url = find_raw_markdown_url(report_html)
    if raw_url:
        with contextlib.suppress(Exception):
            text = fetcher.get_text(raw_url)
            if text.strip():
                return text if text.endswith("\n") else text + "\n"

    main_html = extract_main_html(report_html)
    converter = MarkdownConverter()
    converter.feed(main_html)
    markdown = converter.markdown()
    return f"# {entry.title}\n\nSource report: {entry.report_url}\n\n{markdown}"


def find_raw_markdown_url(report_html: str) -> str | None:
    candidates = set(re.findall(r"https://raw\.githubusercontent\.com/[^\"'<>\\]+\.md", report_html))
    candidates.update(
        github_blob_to_raw(url)
        for url in re.findall(r"https://github\.com/[^\"'<>\\]+/blob/[^\"'<>\\]+\.md", report_html)
    )
    candidates = {url for url in candidates if url}
    for url in sorted(candidates):
        lower = url.lower()
        if "bot-report" not in lower and "readme" not in lower:
            return url
    return None


def github_blob_to_raw(url: str) -> str | None:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", url)
    if not match:
        return None
    owner, repo, branch, path = match.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def extract_main_html(report_html: str) -> str:
    start = report_html.find("<main")
    end = report_html.find("</main>", start)
    if start == -1 or end == -1:
        return report_html
    return report_html[start : end + len("</main>")]


def find_source_repo(report_html: str, slug: str) -> str | None:
    decoded = html.unescape(report_html.replace('\\"', '"'))
    scope_match = re.search(r"<h1[^>]*id=[\"']scope[\"'][\s\S]*?(?=<h1[^>]*id=|</main>)", decoded, re.I)
    search_area = scope_match.group(0) if scope_match else decoded

    links = re.findall(r"https://github\.com/[^\"'<>\\\s]+", search_area)
    cleaned: list[str] = []
    for link in links:
        link = link.rstrip("/).,")
        parsed = urllib.parse.urlparse(link)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            continue
        repo_url = f"https://github.com/{parts[0]}/{parts[1]}"
        if repo_url.endswith("-findings") or repo_url.endswith("/issues"):
            continue
        if GITHUB_REPO_RE.match(repo_url):
            cleaned.append(repo_url)

    if cleaned:
        # Prefer the repo whose name appears in the report slug.
        slug_tail = slug.split("-", 2)[-1]
        for repo in cleaned:
            if slug_tail and slug_tail in repo:
                return repo
        return cleaned[0]
    return None


def clone_repo(repo_url: str, dest: Path) -> None:
    clone_url = repo_url
    token = os.environ.get("GITHUB_TOKEN")
    if token and repo_url.startswith("https://github.com/"):
        clone_url = repo_url.replace("https://", f"https://x-access-token:{token}@")

    cmd = ["git", "clone", "--depth", "1", "--quiet", clone_url, str(dest)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        sanitized = result.stderr.replace(token or "", "***") if token else result.stderr
        raise RuntimeError(f"git clone failed for {repo_url}: {sanitized.strip()}")
    shutil.rmtree(dest / ".git", ignore_errors=True)


def count_solidity_files(root: Path) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*.sol") if path.is_file())


def write_manifest(out: Path, successes: Iterable[SuccessRecord]) -> None:
    projects = sorted((asdict(item) for item in successes), key=lambda x: (x["year"], x["slug"]))
    payload = {
        "source": "code4rena",
        "reports_url": REPORTS_URL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "projects": projects,
    }
    (out / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_failures(out: Path, failures: list[FailureRecord]) -> None:
    if not failures:
        return
    with (out / "failures.jsonl").open("a", encoding="utf-8") as fh:
        for failure in failures:
            fh.write(json.dumps(asdict(failure), ensure_ascii=False) + "\n")


def ensure_output_dirs(out: Path) -> None:
    for name in ("audits", "reports", "contracts"):
        (out / name).mkdir(parents=True, exist_ok=True)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    years = parse_years(args.years)
    out = args.out
    ensure_output_dirs(out)

    fetcher = Fetcher(args.retry, os.environ.get("GITHUB_TOKEN"))
    reports = discover_reports(fetcher, years)
    print(f"Discovered {len(reports)} Code4rena reports for years {sorted(years)}")

    successes: list[SuccessRecord] = []
    failures: list[FailureRecord] = []

    def run(entry: ReportEntry) -> SuccessRecord:
        return process_entry(entry, out, fetcher, args.skip_existing)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(args.concurrency, 1)) as pool:
        future_to_entry = {pool.submit(run, entry): entry for entry in reports}
        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                record = future.result()
                successes.append(record)
                print(f"[ok] {entry.slug} -> {record.id} ({record.solidity_files} .sol)")
            except Exception as err:  # noqa: BLE001 - top-level failure capture for jsonl
                failure = FailureRecord(
                    slug=entry.slug,
                    report_url=entry.report_url,
                    stage="process_entry",
                    reason=str(err),
                )
                failures.append(failure)
                print(f"[fail] {entry.slug}: {err}", file=sys.stderr)

    write_manifest(out, successes)
    if args.include_failures:
        append_failures(out, failures)

    print(f"Completed: {len(successes)} succeeded, {len(failures)} failed. Manifest: {out / 'manifest.json'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
