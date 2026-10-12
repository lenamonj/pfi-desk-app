"""deploykit: shipping your fixed income code, from a public repo to a public app, and keeping it running.

Written day by day in Python for Fixed Income, Course 9: Deployment.

Conventions, the same in every function:
- A server installs only what its code imports. So this module imports the standard library at the top, FastAPI,
  pydantic, and bondmath (standard library only) from day 6, and everything else (pandas, PyYAML, joblib, requests,
  Gradio, Streamlit, agentkit) inside the functions that need it. A service built from deploykit needs fastapi and
  nothing more.
- Nothing here holds or prints a secret. A scan reports where a key-like string is, its kind, its first three
  characters, and its length, never the value.
- Units are in names: price_per_100 and dv01_per_100 per 100 of face, yield_pct in percent, latency_ms in
  milliseconds, sizes in bytes or in MB of 1024 x 1024 bytes, money in US dollars.
- Every served figure states its as-of date. A service returns, refuses, and logs; nothing here is a view on any
  security, issuer, or rate.
"""
from __future__ import annotations  # type hints are read as text, so pandas is imported only where it is used

import re  # the key, email, and address patterns
import subprocess  # running git
from pathlib import Path

# printed by a live-deploy cell when no deployment of your own is set: the cell then does nothing
NO_DEPLOY_MESSAGE = ("No deployment of your own is set in my_bondmath\\.env (MY_SERVICE_URL, MY_SPACE_ID, or HF_TOKEN "
                     "not loaded), so this cell does nothing. After your own deploy, add the line and run it again.")
# what a masked transcript puts in place of each private item
MASKS = {"name": "student", "team": "student-projects", "email": "student@example.com", "id": "<id>", "ip": "<ip>",
         "host": "student"}
# the only email address the course's files and outputs may hold
ALLOWED_EMAIL = "student@example.com"
# key-like strings, each with a minimum length after its prefix so a word in prose does not trip it
KEY_PATTERNS = {
    "sk-or-": re.compile(r"\bsk-or-[A-Za-z0-9-]{8,}"),
    "sk-": re.compile(r"\bsk-(?!or-)[A-Za-z0-9_-]{16,}"),
    "hf_": re.compile(r"\bhf_[A-Za-z0-9]{16,}"),
    "ghp_": re.compile(r"\bghp_[A-Za-z0-9]{16,}"),
    "github_pat_": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"),
    "vercel_": re.compile(r"\bvercel_[A-Za-z0-9]{16,}"),
    "Bearer ": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PLATFORM_HOST = re.compile(r"\b[a-z0-9][a-z0-9-]*\.(vercel\.app|hf\.space)\b", re.IGNORECASE)
_PLATFORM_ID = re.compile(r"\b(?:dpl|prj|team)_[A-Za-z0-9]{6,}\b")
# a file that holds environment values; .env.example holds names only and may be published
_ENV_FILE = re.compile(r"^\.env(?!\.example$)")
MB = 1024 * 1024


def run_git(folder, *args: str) -> str:
    """Run one git command in a folder and return what it printed.

    Inputs: folder, the repository's folder; args, the command's words, for example "log", "--oneline", "-3".
    Output: git's standard output as text.
    Convention: the same as typing git -C folder ... in PowerShell. Raises RuntimeError with git's own message
    (its standard error) when the command fails, so a failed push or merge is never silent.
    """
    result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _hidden(value: str) -> str:
    """How a scan names a match without showing it: its first three characters and its length."""
    return f"starts {value[:3]!r}, {len(value)} characters"


def _text_of(path: Path) -> str | None:
    """A file's text, or None for a binary file (one that holds a zero byte)."""
    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _files(folder: Path) -> list[Path]:
    """Every file under a folder, at any depth, without Git's own .git folder, in a fixed order."""
    return sorted(p for p in folder.rglob("*") if p.is_file() and ".git" not in p.relative_to(folder).parts)


def public_scan(folder, max_mb: float = 5.0):
    """Everything in a folder that must not go public, one row per problem.

    Inputs: folder, the folder you are about to push to a public repo; max_mb, the largest file allowed, in MB of
    1024 x 1024 bytes.
    Output: a DataFrame with columns file (relative to the folder), line (0 for the whole file), kind, and detail.
    Kinds: env_file (a .env file at any depth; .env.example, which holds names only, is allowed), key_like (a match
    of KEY_PATTERNS), email (any address but student@example.com), large_file. Empty means safe to publish.
    Convention: the detail never holds a matched value, only its first three characters and its length. Git's .git
    folder is not scanned (its history is checked by what you commit, not by this scan).
    """
    import pandas as pd

    folder = Path(folder)
    rows = []
    for path in _files(folder):
        name = path.relative_to(folder).as_posix()
        if _ENV_FILE.match(path.name):
            rows.append({"file": name, "line": 0, "kind": "env_file", "detail": "an environment file; never published"})
        size = path.stat().st_size
        if size > max_mb * MB:
            rows.append({"file": name, "line": 0, "kind": "large_file",
                         "detail": f"{size / MB:.1f} MB, over {max_mb:g} MB (MB = 1024 x 1024 bytes)"})
        text = _text_of(path)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in KEY_PATTERNS.items():
                for found in pattern.findall(line):
                    rows.append({"file": name, "line": number, "kind": "key_like",
                                 "detail": f"{kind} pattern, {_hidden(found)}"})
            for found in _EMAIL.findall(line):
                if found.lower() != ALLOWED_EMAIL:
                    rows.append({"file": name, "line": number, "kind": "email", "detail": f"an address, {_hidden(found)}"})
    return pd.DataFrame(rows, columns=["file", "line", "kind", "detail"])


def mask_transcript(text: str, names: list[str]) -> str:
    """A terminal transcript with every private item replaced by the course's masks, safe to share.

    Inputs: text, what a command printed; names, the account names, team slugs, and other words to hide (read on
    the machine that ran the command, never written to a file).
    Output: the text with each name (any case) as "student", every email but student@example.com as
    student@example.com, each IPv4 address as <ip>, the host of every *.vercel.app and *.hf.space address as
    student, and Vercel's deployment, project, and team ids (dpl_..., prj_..., team_...) as <id>.
    Convention: longer names are replaced first, so a team slug that holds a user name is masked whole.
    """
    for name in sorted((n for n in names if n), key=len, reverse=True):
        text = re.sub(re.escape(name), MASKS["name"], text, flags=re.IGNORECASE)
    text = _EMAIL.sub(lambda m: m.group(0) if m.group(0).lower() == ALLOWED_EMAIL else MASKS["email"], text)
    text = _IPV4.sub(MASKS["ip"], text)
    text = _PLATFORM_HOST.sub(lambda m: f"{MASKS['host']}.{m.group(1).lower()}", text)
    return _PLATFORM_ID.sub(MASKS["id"], text)


def show_transcript(path, max_lines: int = 40) -> None:
    """Print a masked transcript the course recorded: one line saying what it is, the command, then the text.

    Inputs: path, a file of data/course9_transcripts/dayNN/; max_lines, the most lines of text to print.
    Output: none; prints. A longer text is cut, and the cut is stated with the number of lines not shown.
    Convention: the file's first three lines are its header (recorded:, command:, masked:).
    """
    lines = Path(path).read_text(encoding="ascii").splitlines()
    header = dict(line.split(": ", 1) for line in lines[:3])
    body = lines[3:]
    print(f"Recorded {header['recorded']} on the course's own account; account names, URLs, and ids masked to "
          f"`student`.")
    print(f"> {header['command']}")
    for line in body[:max_lines]:
        print(line)
    if len(body) > max_lines:
        print(f"[... {len(body) - max_lines} more lines not shown]")


def diff_table(folder, base: str, head: str):
    """What a change adds and removes, file by file: the table a reviewer reads before the diff itself.

    Inputs: folder, the repository; base and head, two commits, branches, or tags (for example "main" and
    "fix-day-count").
    Output: a DataFrame with columns file, added, removed (lines), from git diff --numstat base head. A binary
    file shows 0 and 0.
    """
    import pandas as pd

    rows = []
    for line in run_git(folder, "diff", "--numstat", base, head).splitlines():
        added, removed, name = line.split("\t", 2)
        rows.append({"file": name, "added": int(added) if added != "-" else 0,
                     "removed": int(removed) if removed != "-" else 0})
    return pd.DataFrame(rows, columns=["file", "added", "removed"])


def branch_table(folder):
    """Every local branch beside main: its last commit's subject, and how far it is ahead of and behind main.

    Input: folder, the repository (it must have a branch named main).
    Output: a DataFrame with columns branch, last_subject, ahead (commits on the branch not on main), behind
    (commits on main not on the branch), one row per branch in name order, main itself included (0 and 0).
    """
    import pandas as pd

    rows = []
    for branch in sorted(run_git(folder, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()):
        subject = run_git(folder, "log", "-1", "--format=%s", branch).strip()
        behind, ahead = run_git(folder, "rev-list", "--left-right", "--count", f"main...{branch}").split()
        rows.append({"branch": branch, "last_subject": subject, "ahead": int(ahead), "behind": int(behind)})
    return pd.DataFrame(rows, columns=["branch", "last_subject", "ahead", "behind"])


def conflict_files(folder) -> list[str]:
    """The files a merge left in conflict, which you must read and resolve before you commit.

    Input: folder, the repository, in the middle of a merge that stopped.
    Output: the file names Git lists as unmerged (git diff --name-only --diff-filter=U), sorted; empty when there
    is no conflict.
    """
    return sorted(run_git(folder, "diff", "--name-only", "--diff-filter=U").split())


ACTION_TAGS = {"checkout": "actions/checkout@v7", "setup-python": "actions/setup-python@v7"}
_VERSION_TAG = re.compile(r"@(?:v\d+(?:\.\d+)*|[0-9a-f]{40})$")


def workflow_text(python_versions=("3.12", "3.13"), requirements: str = "requirements.txt",
                  tests: str = "test_bondmath.py") -> str:
    """The course's GitHub Actions workflow: run the tests on a fresh Linux machine on every push and pull request.

    Inputs: python_versions, the Pythons of the matrix, as text; requirements, the requirements file the runner
    installs; tests, the test file pytest runs.
    Output: the YAML text of .github/workflows/tests.yml. Every version is written in quotes, so YAML reads "3.10" as
    text and never as the number 3.1; each action is pinned to a version tag, never to a branch.
    Convention: the run: lines run in bash on the Linux runner; you never type them.
    """
    versions = ", ".join(f'"{version}"' for version in python_versions)
    return f"""name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [{versions}]
    steps:
      - uses: {ACTION_TAGS["checkout"]}
      - uses: {ACTION_TAGS["setup-python"]}
        with:
          python-version: ${{{{ matrix.python-version }}}}
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r {requirements}
      - run: python -m pytest -q {tests}
"""


def _workflow(text: str) -> dict:
    """A workflow read by yaml.safe_load. YAML 1.1 reads the key on as True, so it is put back under "on"."""
    import yaml

    data = yaml.safe_load(text)
    if True in data:
        data["on"] = data.pop(True)
    return data


def workflow_steps(text: str):
    """Each step of each job of a workflow, as a table you can read line by line.

    Input: text, a workflow's YAML.
    Output: a DataFrame with columns job, step (1, 2, ...), uses (the action, or empty), run (the command, or
    empty), shell (the step's own shell, else bash on a Linux or macOS runner and pwsh on a Windows runner).
    """
    import pandas as pd

    rows = []
    for job, spec in _workflow(text)["jobs"].items():
        default = "pwsh" if "windows" in str(spec.get("runs-on", "")) else "bash"
        for number, step in enumerate(spec.get("steps", []), start=1):
            rows.append({"job": job, "step": number, "uses": step.get("uses", ""), "run": step.get("run", ""),
                         "shell": step.get("shell", default) if "run" in step else ""})
    return pd.DataFrame(rows, columns=["job", "step", "uses", "run", "shell"])


def check_workflow(text: str) -> list[str]:
    """The problems of a workflow that would still run, each as a sentence; empty means none found.

    Input: text, a workflow's YAML.
    Output: one sentence per problem: an action on a branch or with no tag (actions/checkout@main) rather than a
    version tag or a commit; a python-version that yaml.safe_load reads as a number (3.10 is read as 3.1); no step
    that runs pytest; no pull_request trigger; a run line that prints a secrets. expression.
    """
    data = _workflow(text)
    problems = []
    triggers = data.get("on", [])
    if "pull_request" not in (triggers if isinstance(triggers, (list, dict)) else [triggers]):
        problems.append("no pull_request trigger: a pull request is merged without its tests running")
    found_pytest = False
    for job, spec in data.get("jobs", {}).items():
        matrix = spec.get("strategy", {}).get("matrix", {})
        versions = matrix.get("python-version", [])
        for version in versions if isinstance(versions, list) else [versions]:
            if not isinstance(version, str):
                problems.append(f"job {job}: python-version {version!r} is read as a number; write it in quotes")
        for number, step in enumerate(spec.get("steps", []), start=1):
            uses = step.get("uses", "")
            if uses and not _VERSION_TAG.search(uses):
                problems.append(f"job {job}, step {number}: {uses} is not pinned to a version tag or a commit")
            version = step.get("with", {}).get("python-version")
            if version is not None and not isinstance(version, str):
                problems.append(f"job {job}, step {number}: python-version {version!r} is read as a number")
            run = str(step.get("run", ""))
            found_pytest = found_pytest or "pytest" in run
            if "secrets." in run and re.search(r"\b(?:echo|print|Write-Host|cat)\b", run):
                problems.append(f"job {job}, step {number}: a run line prints a secrets. expression")
    if not found_pytest:
        problems.append("no step runs pytest")
    return problems


import ast  # reading a file's imports without running it
import importlib.metadata  # installed distributions: names, versions, files, requirements
import sys  # the standard library's module names

# distributions that install only on Windows: a server's requirements need a marker for them
WINDOWS_ONLY = ("pywin32", "pywinpty")


def _normal(name: str) -> str:
    """A distribution name as pip compares them: lower case, with -, _, and . the same."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements_for(paths) -> list[str]:
    """The requirements file lines a server needs to run these Python files: what they import, nothing more.

    Input: paths, the Python files that will run on the server.
    Output: sorted lines "distribution==version": every third-party top-level import found by ast (not the
    standard library, not a module whose file sits beside the given files), mapped to the distribution that
    installs it through importlib.metadata.packages_distributions() (yaml is PyYAML, sklearn is scikit-learn, dotenv
    is python-dotenv), pinned to the version installed in the running environment.
    Raises ValueError naming an import no installed distribution provides.
    Convention: an import inside a function counts too, because the server runs it when the function runs.
    """
    paths = [Path(p) for p in paths]
    local = {p.stem for folder in {p.parent for p in paths} for p in folder.glob("*.py")}
    found = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    third_party = sorted(found - set(sys.stdlib_module_names) - local - {"__future__"})
    providers = importlib.metadata.packages_distributions()
    lines = set()
    for module in third_party:
        if module not in providers:
            raise ValueError(f"no installed distribution provides the import {module!r}")
        for distribution in providers[module]:
            lines.add(f"{distribution}=={importlib.metadata.version(distribution)}")
    return sorted(lines, key=str.lower)


def _required(distribution) -> list[str]:
    """The distributions one distribution requires in this environment: no extras, markers evaluated here."""
    from packaging.requirements import Requirement

    names = []
    for text in distribution.requires or []:
        requirement = Requirement(text)
        if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
            names.append(requirement.name)
    return names


def installed_size(distributions):
    """What installing some distributions puts on disk, with everything they require, each counted once.

    Input: distributions, names or requirement lines ("fastapi" or "fastapi==0.143.0").
    Output: a DataFrame with columns distribution, version, bytes, largest first: the given distributions and
    every distribution they require (followed through importlib.metadata, extras left out), each once, with its
    bytes summed from the sizes in its RECORD file in the running environment.
    Convention: sizes are this machine's. Wheels differ by platform: a Windows wheel is not the size of the Linux
    wheel a server installs, so a server's size is measured on Linux wheels.
    Raises importlib.metadata.PackageNotFoundError for a distribution that is not installed.
    """
    import pandas as pd

    seen, queue, rows = set(), [re.split(r"[=<>!~ ;\[]", d.strip(), maxsplit=1)[0] for d in distributions], []
    while queue:
        name = queue.pop(0)
        if _normal(name) in seen:
            continue
        seen.add(_normal(name))
        distribution = importlib.metadata.distribution(name)
        size = sum(f.size or 0 for f in distribution.files or [])
        rows.append({"distribution": distribution.metadata["Name"], "version": distribution.version, "bytes": size})
        queue += _required(distribution)
    frame = pd.DataFrame(rows, columns=["distribution", "version", "bytes"])
    return frame.sort_values(["bytes", "distribution"], ascending=[False, True], ignore_index=True)


def pins_check(text: str) -> list[str]:
    """The problems of a server's requirements file, each as a sentence; empty means none found.

    Input: text, the file's text.
    Output: one sentence per problem: a line not pinned with ==; a Windows-only distribution (WINDOWS_ONLY) without
    a sys_platform marker, which a Linux server cannot install; a distribution listed twice.
    Convention: blank lines and # comments are skipped. pip freeze lists everything one machine has installed, its
    Windows-only distributions included, so it is not a server's requirements file.
    """
    problems, seen = [], set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = _normal(re.split(r"[=<>!~ ;\[]", line, maxsplit=1)[0])
        if "==" not in line:
            problems.append(f"line {number}: {line} is not pinned with ==")
        if name in WINDOWS_ONLY and "sys_platform" not in line:
            problems.append(f"line {number}: {name} installs only on Windows; add ; sys_platform == \"win32\"")
        if name in seen:
            problems.append(f"line {number}: {name} is listed twice")
        seen.add(name)
    return problems


import json  # gh's JSON output; from day 8, the snapshot and the request log

# a run that did not complete a test: neither a pass nor a failure, so pass_rate leaves it out of both counts
NOT_COUNTED = ("cancelled", "skipped", "")


def ci_history(transcript_json: str):
    """A table of CI runs from the JSON gh run list prints.

    Input: transcript_json, the text of gh run list --json databaseId,headBranch,event,conclusion,createdAt; a
    masked transcript's three header lines before it are skipped.
    Output: a DataFrame with columns run (the run's number), branch, event (push, pull_request, ...), conclusion
    (success, failure, cancelled, skipped, or empty while a run is in progress), created (a UTC timestamp), oldest
    first.
    """
    import pandas as pd

    text = transcript_json[transcript_json.index("["):]
    rows = [{"run": item["databaseId"], "branch": item["headBranch"], "event": item["event"],
             "conclusion": item.get("conclusion") or "", "created": item["createdAt"]} for item in json.loads(text)]
    frame = pd.DataFrame(rows, columns=["run", "branch", "event", "conclusion", "created"])
    frame["created"] = pd.to_datetime(frame["created"], utc=True)
    return frame.sort_values(["created", "run"], ignore_index=True)


def pass_rate(history, branch: str = "main") -> float:
    """The share of a branch's completed CI runs that passed.

    Inputs: history, from ci_history; branch, the branch to count.
    Output: runs with conclusion success divided by the runs that completed a test, as a fraction from 0 to 1.
    Convention: a cancelled or skipped run, or one still in progress, is neither a pass nor a failure, so it is left
    out of both counts (NOT_COUNTED). Raises ValueError when the branch has no completed run.
    """
    runs = history[(history["branch"] == branch) & ~history["conclusion"].isin(NOT_COUNTED)]
    if runs.empty:
        raise ValueError(f"no completed run on {branch}")
    return float((runs["conclusion"] == "success").mean())


import socket  # is a port free?
import sys  # the Python that starts the server
import time  # waiting for the server to answer
import urllib.request  # the one request that checks the server is up
from contextlib import contextmanager
from datetime import date
from typing import Literal

import fastapi  # the web framework: a function behind an address
import pydantic  # typed requests and responses

import bondmath  # Course 2's module, unchanged: every number the bond service returns

VERSION = "1.0"


def _maturity_after_settlement(maturity: date, info) -> date:
    """The rule both request models share: a maturity after the settlement date, else a 422 naming maturity."""
    if "settlement" in info.data and maturity <= info.data["settlement"]:
        raise ValueError("maturity must be after settlement")
    return maturity


class BondRequest(pydantic.BaseModel):
    """A fixed-rate bullet bond and a yield, as a request body. Every field is required; units are in the names."""
    settlement: date = pydantic.Field(description="settlement date, ISO text such as 2026-10-02")
    maturity: date = pydantic.Field(description="maturity date, ISO text, after settlement")
    coupon_pct: float = pydantic.Field(strict=True, description="annual coupon in percent: 5.0 for 5%")
    yield_pct: float = pydantic.Field(strict=True, description="annual yield to maturity in percent: 5.06")
    frequency: Literal[1, 2, 4] = pydantic.Field(description="coupons a year: 1, 2, or 4")

    @pydantic.field_validator("maturity")
    @classmethod
    def _after_settlement(cls, maturity: date, info) -> date:
        return _maturity_after_settlement(maturity, info)


class YieldRequest(pydantic.BaseModel):
    """A fixed-rate bullet bond and its clean price, as a request body for /yield. Every field is required."""
    settlement: date = pydantic.Field(description="settlement date, ISO text such as 2026-10-02")
    maturity: date = pydantic.Field(description="maturity date, ISO text, after settlement")
    coupon_pct: float = pydantic.Field(strict=True, description="annual coupon in percent: 5.0 for 5%")
    clean_price_per_100: float = pydantic.Field(strict=True, description="clean price per 100 of face")
    frequency: Literal[1, 2, 4] = pydantic.Field(description="coupons a year: 1, 2, or 4")

    @pydantic.field_validator("maturity")
    @classmethod
    def _after_settlement(cls, maturity: date, info) -> date:
        return _maturity_after_settlement(maturity, info)


class PriceResponse(pydantic.BaseModel):
    """A clean price, per 100 of face."""
    price_per_100: float


class AccruedResponse(pydantic.BaseModel):
    """Accrued interest, per 100 of face."""
    accrued_per_100: float


class YieldResponse(pydantic.BaseModel):
    """A yield to maturity, in percent a year."""
    yield_pct: float


class DV01Response(pydantic.BaseModel):
    """DV01: price points per 100 of face for a 1 bp fall in yield."""
    dv01_per_100: float


def bond_values(endpoint: str, body: dict) -> dict:
    """What the bond service returns for one request body, computed here with bondmath, without a server.

    Inputs: endpoint, "/price", "/accrued", "/dv01", or "/yield"; body, the request body as a dict.
    Output: the response body as a dict, for example {"dv01_per_100": 0.043624879198739516}.
    Convention: the same function the endpoints run, so a deployed value equals this one exactly.
    """
    if endpoint == "/yield":
        bond = YieldRequest.model_validate(body)
        return {"yield_pct": bondmath.yield_to_maturity(bond.settlement, bond.maturity, bond.coupon_pct,
                                                        bond.clean_price_per_100, bond.frequency)}
    bond = BondRequest.model_validate(body)
    arguments = (bond.settlement, bond.maturity, bond.coupon_pct)
    if endpoint == "/price":
        return {"price_per_100": bondmath.price(*arguments, bond.yield_pct, bond.frequency)}
    if endpoint == "/accrued":
        return {"accrued_per_100": bondmath.accrued_interest(*arguments, bond.frequency)}
    if endpoint == "/dv01":
        return {"dv01_per_100": bondmath.dv01(*arguments, bond.yield_pct, bond.frequency)}
    raise ValueError(f"no bond endpoint {endpoint!r}")


def bond_app() -> fastapi.FastAPI:
    """The bond service: bondmath behind four POST endpoints and a health check.

    Output: a FastAPI app with GET /health ({"status": "ok", "version": ..., "as_of": None}: the bond service holds
    no data, so its figures are as of each request's settlement date), POST /price, /accrued, and /dv01 (a
    BondRequest), and POST /yield (a YieldRequest). Each returns bondmath's value unchanged, under a key with its unit.
    Convention: a body with a field missing, a number sent as text, or a maturity not after settlement is refused
    with HTTP 422 naming the field, before bondmath runs.
    """
    app = fastapi.FastAPI(title="PFI bond service", version=VERSION)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "as_of": None}

    @app.post("/price")
    def price(bond: BondRequest) -> PriceResponse:
        return PriceResponse(**bond_values("/price", bond.model_dump()))

    @app.post("/accrued")
    def accrued(bond: BondRequest) -> AccruedResponse:
        return AccruedResponse(**bond_values("/accrued", bond.model_dump()))

    @app.post("/dv01")
    def dv01(bond: BondRequest) -> DV01Response:
        return DV01Response(**bond_values("/dv01", bond.model_dump()))

    @app.post("/yield")
    def yield_to_maturity(bond: YieldRequest) -> YieldResponse:
        return YieldResponse(**bond_values("/yield", bond.model_dump()))

    return app


def _port_held(port: int) -> bool:
    """True when something on this machine already listens on 127.0.0.1 at the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


@contextmanager
def serve(module: str, app: str, port: int = 8765, timeout_s: float = 20.0):
    """Run one real server for the length of a with block, then stop it: for the one lesson that needs a port.

    Inputs: module and app, where the app lives ("service", "app" for app = ... in service.py, in the current
    folder); port, on 127.0.0.1 only, so nothing outside this machine can reach it; timeout_s, how long to wait for
    the server to start and, at the end, for the port to be free again.
    Output: the base URL, for example "http://127.0.0.1:8765", inside the with block.
    Convention: refuses to start when the port is held. Starts python -m uvicorn module:app --host 127.0.0.1
    --port N --log-level warning --no-access-log, with the server's messages in uvicorn_N.log in the current folder,
    waits until GET /health answers, and in finally stops the process and waits until the port is free. Raises
    RuntimeError when the port is held, when the server stops or does not answer in time (with the log's text), or
    when the port is still held after it stopped.
    """
    if _port_held(port):
        raise RuntimeError(f"port {port} is already in use on 127.0.0.1: stop what holds it, or pass another port")
    log_path = Path.cwd() / f"uvicorn_{port}.log"
    base = f"http://127.0.0.1:{port}"
    command = [sys.executable, "-m", "uvicorn", f"{module}:{app}", "--host", "127.0.0.1", "--port", str(port),
               "--log-level", "warning", "--no-access-log"]
    with open(log_path, "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, cwd=Path.cwd())
    try:
        deadline = time.monotonic() + timeout_s
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"the server stopped at start: {log_path.read_text(encoding='utf-8')[-500:]}")
            try:
                with urllib.request.urlopen(base + "/health", timeout=1) as answer:
                    if answer.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"the server did not answer /health within {timeout_s:g} s")
            time.sleep(0.1)
        yield base
    finally:
        process.terminate()
        process.wait(timeout=timeout_s)
        deadline = time.monotonic() + timeout_s
        while _port_held(port):
            if time.monotonic() > deadline:
                raise RuntimeError(f"port {port} is still held {timeout_s:g} s after the server stopped")
            time.sleep(0.1)


import shutil  # copying the modules into a deploy folder

DISCLAIMER = ("This course is educational content created in a personal capacity. Nothing here is investment advice or "
              "a recommendation to buy or sell any security. All portfolio data is synthetic.")
# the file names Vercel's Python runtime looks for an app in (its runtime page, read on the day 7 build day)
ENTRYPOINTS = ("app.py", "main.py", "index.py", "server.py", "api/index.py", "api/app.py", "api/main.py")
VERCEL_PYTHON = "3.13"


def vercel_folder(folder, modules: list) -> list:
    """A folder Vercel can deploy as the bond service, with nothing in it but what the service needs.

    Inputs: folder, a new folder (created if missing); modules, the Python files the app imports (bondmath.py and
    deploykit.py), copied beside it unchanged.
    Output: the files written, as Paths: app.py (app = deploykit.bond_app()), the modules, requirements.txt (one
    line: fastapi pinned to the installed version), .python-version (3.13), and README.md with the disclaimer.
    Convention: Vercel runs an ASGI app with no other configuration when requirements.txt holds FastAPI and an
    entrypoint file defines app (its Python runtime page, read on the build day).
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    files = {
        "app.py": '"""The bond service on Vercel: bondmath behind HTTP, from deploykit."""\nimport deploykit\n\n'
                  "app = deploykit.bond_app()\n",
        "requirements.txt": f"fastapi=={importlib.metadata.version('fastapi')}\n",
        ".python-version": f"{VERCEL_PYTHON}\n",
        "README.md": ("# PFI bond service\n\nBond math behind HTTP: POST /price, /yield, /accrued, and /dv01 return a "
                      "clean price, a yield, accrued interest, and DV01, each per 100 of face or in percent, for the "
                      "bond in the request. It holds no data and no key.\n\n" + DISCLAIMER + "\n"),
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
        written.append(folder / name)
    for module in modules:
        written.append(Path(shutil.copy(module, folder / Path(module).name)))
    return sorted(written, key=lambda path: path.name)


def _defines_app(path: Path) -> bool:
    """True when a Python file assigns the name app at its top level."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
               for node in tree.body)


def check_deploy_folder(folder, limit_mb: float = 500.0) -> list[str]:
    """The problems of a folder you are about to deploy, each as a sentence; empty means none found.

    Inputs: folder, the deploy folder; limit_mb, the platform's limit on its size, in MB of 1024 x 1024 bytes
    (Vercel's bundle limit is 500 MB, as read on the build day).
    Output: one sentence per problem: a .env file at any depth (.env.example, names only, is allowed); a
    KEY_PATTERNS match in any text file, of any name; no requirements.txt, or a problem pins_check finds in it; no
    entrypoint file (ENTRYPOINTS) that defines app; a folder over the limit.
    Convention: a match is named by its file, line, and kind, never by its value.
    """
    folder = Path(folder)
    found = public_scan(folder, max_mb=limit_mb)
    problems = [f"{row.file}: an environment file at any depth is never deployed"
                for row in found[found["kind"] == "env_file"].itertuples()]
    problems += [f"{row.file}, line {row.line}: a key-like string ({row.detail})"
                 for row in found[found["kind"] == "key_like"].itertuples()]
    requirements = folder / "requirements.txt"
    if not requirements.is_file():
        problems.append("no requirements.txt: the platform cannot know what to install")
    else:
        problems += [f"requirements.txt {problem}" for problem in pins_check(requirements.read_text(encoding="utf-8"))]
    if not any((folder / name).is_file() and _defines_app(folder / name) for name in ENTRYPOINTS):
        problems.append(f"no entrypoint defines app (looked in {', '.join(ENTRYPOINTS)})")
    total = sum(path.stat().st_size for path in _files(folder))
    if total > limit_mb * MB:
        problems.append(f"the folder is {total / MB:.1f} MB, over the {limit_mb:g} MB limit")
    return problems


def check_live(base_url: str, cases: list[dict], session=None):
    """Your deployed service against bondmath on your machine, case by case: for a live-deploy cell only.

    Inputs: base_url, your deployment's address (MY_SERVICE_URL); cases, each {"endpoint": "/dv01", "body":
    {...}}; session, a requests.Session or anything with its post method (a test passes a fake one).
    Output: a DataFrame with columns endpoint, local, deployed, equal: the value bond_values computes here, the
    value your service returned, and whether they are exactly equal.
    Convention: sends one POST per case to your own deployment, never to anyone else's. With no base_url (None or
    empty: MY_SERVICE_URL not loaded) it prints NO_DEPLOY_MESSAGE, sends nothing, and returns an empty table. Raises
    RuntimeError naming the endpoint and the status when the service does not return 200.
    """
    import pandas as pd

    if not base_url:
        print(NO_DEPLOY_MESSAGE)
        return pd.DataFrame(columns=["endpoint", "local", "deployed", "equal"])
    if session is None:
        import requests

        session = requests.Session()
    rows = []
    for case in cases:
        local = bond_values(case["endpoint"], case["body"])
        reply = session.post(base_url.rstrip("/") + case["endpoint"], json=case["body"], timeout=30)
        if reply.status_code != 200:
            raise RuntimeError(f"{case['endpoint']} returned HTTP {reply.status_code}")
        key = next(iter(local))
        deployed = reply.json()[key]
        rows.append({"endpoint": case["endpoint"], "local": local[key], "deployed": deployed,
                     "equal": deployed == local[key]})
    return pd.DataFrame(rows, columns=["endpoint", "local", "deployed", "equal"])


import hashlib  # the SHA-256 of every saved exchange a snapshot came from

# the date every figure of the Course 8 desk brief is from: the capstone's saved runs, as of 2026-10-02
DESK_AS_OF = "2026-10-02"
# Course 8's refusal line (agentkit.REFUSAL), written here so a server needs no agentkit; a test asserts it is the same
REFUSAL_LINE = "REFUSED: this course asks only what the document says"
NOT_SAVED = "not in the saved runs: this service answers only the questions Course 8's capstone recorded"
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _question_key(text: str) -> str:
    """A question as the snapshot looks it up: spaces collapsed, any case."""
    return " ".join(text.split()).casefold()


def desk_snapshot(brief, checks, run, saved_folder, answers=None, as_of: str = DESK_AS_OF) -> dict:
    """The Course 8 desk brief, frozen as data a small service can serve: every figure traced to a saved exchange.

    Inputs: brief, the DeskBrief run_desk returned in replay; checks, the table check_brief returned; run, the
    brief's run (its exchanges); saved_folder, the folder of saved exchanges it replayed from
    (data/course8_agent_runs/day15); answers, {question: the saved answer text} for the recorded questions /ask may
    answer; as_of, the date the figures are from.
    Output: a dict ready for json.dump: as_of, mode ("replay"), brief (DeskBrief.model_dump()), checks (one record
    per check), run_line (agentkit.run_line in replay), exchanges ([{"key", "sha256"}], one per saved exchange the
    run used, in order), answers, the disclaimer, and guard: Course 8's input rule as data (agentkit.opinion_guard's
    words and negation, credit_desk's ordering and holding patterns and real issuers, the refusal line), so the
    service refuses a request for a view with no agentkit installed.
    Raises ValueError when an exchange of the run is not in saved_folder: a snapshot holds only what was saved.
    """
    import agentkit
    import credit_desk
    import mlkit
    import textkit

    saved_folder = Path(saved_folder)
    exchanges, seen = [], set()
    for exchange in run["exchanges"]:
        if exchange["key"] in seen:
            continue
        seen.add(exchange["key"])
        path = saved_folder / f"{exchange['key']}.json"
        if not path.is_file():
            raise ValueError(f"exchange {exchange['key'][:12]} is not in {saved_folder.name}")
        exchanges.append({"key": exchange["key"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    guard = {"words": list(mlkit.FORECAST_WORDS) + list(textkit.OPINION_WORDS),
             "negation": agentkit._NEGATION.pattern, "ordering": credit_desk.ORDERING.pattern,
             "holding": credit_desk.HOLDING.pattern, "real_issuers": list(credit_desk.REAL_ISSUERS),
             "refusal": agentkit.REFUSAL}
    return {"as_of": as_of, "mode": "replay", "brief": brief.model_dump(),
            "checks": json.loads(checks.to_json(orient="records")), "run_line": agentkit.run_line(run, "replay"),
            "exchanges": exchanges, "answers": dict(answers or {}), "disclaimer": DISCLAIMER, "guard": guard}


def _refusal_reasons(question: str, guard: dict) -> list[str]:
    """The rules a question breaks, read from its words before anything is looked up (credit_desk.input_check's
    rules, from the snapshot's guard): an opinion or forecast word outside a negation, an ordering of securities,
    or a real issuer's name beside a holding."""
    reasons = []
    negation = re.compile(guard["negation"], re.IGNORECASE)
    for sentence in _SENTENCE.split(question):
        if negation.search(sentence):
            continue
        if any(re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", sentence, re.IGNORECASE) for word in guard["words"]):
            reasons.append("opinion words")
            break
    if re.search(guard["ordering"], question, re.IGNORECASE):
        reasons.append("an ordering of securities")
    if re.search(guard["holding"], question, re.IGNORECASE) and any(
            re.search(rf"\b{re.escape(name)}\b", question) for name in guard["real_issuers"]):
        reasons.append("a real issuer beside a holding")
    return reasons


class AskRequest(pydantic.BaseModel):
    """A question to the desk service."""
    question: str = pydantic.Field(min_length=1, max_length=1000, description="one question, in words")


class AskResponse(pydantic.BaseModel):
    """The desk service's answer: the saved answer, or the refusal line, with the date its figures are from."""
    question: str
    answer: str
    refused: bool
    as_of: str


def desk_app(snapshot: dict, settings: dict) -> fastapi.FastAPI:
    """The desk service: the Course 8 brief from a snapshot, with no key on the server.

    Inputs: snapshot, from desk_snapshot (or its JSON file, loaded); settings, from live_settings.
    Output: a FastAPI app. GET /health ({"status", "version", "as_of", "mode"}; never a value from the
    environment); GET /brief ({"as_of", "mode", "brief"}); GET /checks ({"as_of", "checks"}); POST /ask (an
    AskRequest): a request for a view gets the refusal line with refused true and HTTP 200, before anything is looked
    up; a recorded question gets its saved answer; any other gets HTTP 404 with NOT_SAVED.
    Convention: a refused answer also carries the header X-Desk-Refused: true, so a request log can count refusals
    without reading a body. The service answers from the snapshot in either mode: a live desk would need Course 8's
    whole toolkit and a key on the server, which this course never deploys.
    """
    app = fastapi.FastAPI(title="PFI desk brief", version=VERSION)
    answers = {_question_key(q): a for q, a in snapshot["answers"].items()}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "as_of": snapshot["as_of"], "mode": settings["mode"]}

    @app.get("/brief")
    def brief() -> dict:
        return {"as_of": snapshot["as_of"], "mode": snapshot["mode"], "brief": snapshot["brief"]}

    @app.get("/checks")
    def checks() -> dict:
        return {"as_of": snapshot["as_of"], "checks": snapshot["checks"]}

    @app.post("/ask")
    def ask(request: AskRequest, response: fastapi.Response) -> AskResponse:
        if _refusal_reasons(request.question, snapshot["guard"]):
            response.headers["X-Desk-Refused"] = "true"
            return AskResponse(question=request.question, answer=snapshot["guard"]["refusal"], refused=True,
                               as_of=snapshot["as_of"])
        key = _question_key(request.question)
        if key not in answers:
            raise fastapi.HTTPException(status_code=404, detail=NOT_SAVED)
        return AskResponse(question=request.question, answer=answers[key], refused=False, as_of=snapshot["as_of"])

    return app


def live_settings(environ) -> dict:
    """Which mode a deployed desk runs in, read from the platform's settings, without holding any value.

    Input: environ, os.environ or any mapping of names to values.
    Output: {"mode": "live" or "replay", "key_loaded": True or False}. Live only when DESK_MODE is "live" and
    OPENAI_API_KEY is set; anything else is replay. Never returns a value from environ.
    """
    key_loaded = bool(environ.get("OPENAI_API_KEY"))
    mode = "live" if environ.get("DESK_MODE") == "live" and key_loaded else "replay"
    return {"mode": mode, "key_loaded": key_loaded}


SECTIONS = ("macro", "documents", "portfolio")
# a chat message asking for the last question again: the handler reads the last user question from the history
FOLLOW_UPS = ("again", "repeat", "same question", "the same again")


def brief_frames(snapshot: dict) -> dict:
    """The snapshot's tables, shared by every front end: one per brief section, and the checks.

    Input: snapshot, from desk_snapshot.
    Output: {"macro": ..., "documents": ..., "portfolio": ..., "checks": ...}, each a DataFrame. A section's
    frame has one row per figure (name, value, unit, tool_call_id, and in documents section and status); the
    checks frame is the check table.
    """
    import pandas as pd

    frames = {}
    for name in SECTIONS:
        columns = ["name", "value", "unit", "tool_call_id"] + (["section", "status"] if name == "documents" else [])
        frames[name] = pd.DataFrame(snapshot["brief"][name]["figures"], columns=columns)
    frames["checks"] = pd.DataFrame(snapshot["checks"], columns=["section", "check", "item", "passed", "detail"])
    return frames


def _text(content) -> str:
    """The text of a chat message or a history item's content: a string, a dict with "text", or Gradio 6's list of
    typed parts ([{"type": "text", "text": ...}]), whose text parts are joined."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return " ".join(part["text"] for part in content if isinstance(part, dict) and part.get("type") == "text")


def chat_reply(message, history, snapshot: dict) -> str:
    """The desk chat's handler: a recorded question gets its saved answer, nothing else does.

    Inputs: message, the new message (text, or Gradio 6's typed parts); history, the conversation Gradio hands the
    handler, a list of {"role", "content"} items whose content is a list of typed parts in Gradio 6; snapshot,
    from desk_snapshot.
    Output: the reply text: the refusal line for a request for a view (checked first, before any lookup); the saved
    answer, with its as-of date, for a recorded question; else NOT_SAVED. A follow-up (FOLLOW_UPS, such as "again")
    answers the last question the user sent in the history.
    Convention: the history on the screen is not a model's conversation: nothing here is sent anywhere.
    """
    question = _text(message).strip()
    if _question_key(question) in FOLLOW_UPS:
        asked = [_text(item["content"]) for item in history if item.get("role") == "user"]
        asked = [text for text in asked if _question_key(text) not in FOLLOW_UPS]
        if not asked:
            return NOT_SAVED
        question = asked[-1]
    if _refusal_reasons(question, snapshot["guard"]):
        return snapshot["guard"]["refusal"]
    answers = {_question_key(q): a for q, a in snapshot["answers"].items()}
    answer = answers.get(_question_key(question))
    return f"{answer}\n\n(As of {snapshot['as_of']} in the course's saved runs.)" if answer else NOT_SAVED


def bond_calculator(settlement: str, maturity: str, coupon_pct: float, yield_pct: float, frequency: int) -> str:
    """The calculator tab's handler: price, accrued interest, and DV01 per 100 of face for one bond, as text.

    Inputs as BondRequest's fields (dates as ISO text). Output: three lines, or the reason the inputs were refused.
    """
    body = {"settlement": settlement, "maturity": maturity, "coupon_pct": float(coupon_pct),
            "yield_pct": float(yield_pct), "frequency": int(frequency)}
    try:
        values = {endpoint: next(iter(bond_values(endpoint, body).values())) for endpoint in ("/price", "/accrued",
                                                                                             "/dv01")}
    except pydantic.ValidationError as error:
        return "Refused: " + "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in error.errors())
    return (f"Clean price: {values['/price']:.6f} per 100 of face\nAccrued interest: {values['/accrued']:.6f} per 100 "
            f"of face\nDV01: {values['/dv01']:.6f} price points per 100 of face")


def gradio_app(snapshot: dict):
    """The desk brief as a Gradio app with four tabs: the brief, the checks, a bond calculator, and the chat.

    Input: snapshot, from desk_snapshot.
    Output: a gr.Blocks, built and not launched (a notebook never launches it; demo.launch() runs it from
    PowerShell, and a Space runs it on Hugging Face). Every tab states the as-of date and the disclaimer.
    Convention: analytics_enabled=False on the app and the chat. Gradio's default sends usage data and checks for a
    newer version over the network as soon as a Blocks is built; this app sends nothing.
    """
    import gradio as gr

    frames = brief_frames(snapshot)
    with gr.Blocks(title="PFI desk brief", analytics_enabled=False) as demo:
        gr.Markdown(f"# PFI desk brief\n\nFigures as of {snapshot['as_of']} in the course's saved runs. "
                    f"{snapshot['disclaimer']}")
        with gr.Tab("Brief"):
            for name in SECTIONS:
                gr.Markdown(f"## {name.title()}\n\n{snapshot['brief'][name]['text']}")
                gr.Dataframe(frames[name], label=f"{name} figures")
        with gr.Tab("Checks"):
            gr.Dataframe(frames["checks"], label="checks")
        with gr.Tab("Bond calculator"):
            inputs = [gr.Textbox(value="2026-10-02", label="settlement"), gr.Textbox(value="2031-10-02",
                                                                                   label="maturity"),
                      gr.Number(value=5.0, label="coupon_pct"), gr.Number(value=5.06, label="yield_pct"),
                      gr.Dropdown(choices=[1, 2, 4], value=2, label="frequency")]
            result = gr.Textbox(label="result")
            gr.Button("Compute").click(bond_calculator, inputs=inputs, outputs=result)
        with gr.Tab("Chat"):
            gr.ChatInterface(lambda message, history: chat_reply(message, history, snapshot), title="Ask the brief",
                             analytics_enabled=False)
    return demo


def streamlit_source(snapshot_path) -> str:
    """The text of streamlit_app.py: the brief, the checks, and a download button for the checks as CSV.

    Input: snapshot_path, the snapshot's JSON file, as the app will find it (relative to where it runs).
    Output: the file's text. Run it with streamlit run streamlit_app.py from PowerShell; test it with Streamlit's
    AppTest, which needs no server and no browser.
    """
    return f'''"""The desk brief in Streamlit: the snapshot's sections and checks, and the checks as a CSV download."""
import json
from pathlib import Path

import streamlit as st

import deploykit

snapshot = json.loads(Path({str(snapshot_path)!r}).read_text(encoding="utf-8"))
frames = deploykit.brief_frames(snapshot)
st.title("PFI desk brief")
st.caption(f"Figures as of {{snapshot['as_of']}} in the course's saved runs. {{snapshot['disclaimer']}}")
for name in deploykit.SECTIONS:
    st.subheader(name.title())
    st.write(snapshot["brief"][name]["text"])
    st.dataframe(frames[name])
st.subheader("Checks")
st.dataframe(frames["checks"])
st.download_button("Download the checks as CSV", data=frames["checks"].to_csv(index=False),
                   file_name="desk_checks.csv", mime="text/csv")
'''


GRADIO_SDK_VERSION = "6.30.0"
SPACE_PYTHON = "3.12.12"
SPACE_PLACEHOLDER = '''try:
    import spaces  # only on Hugging Face

    @spaces.GPU
    def _placeholder():  # ZeroGPU refuses an app with no @spaces.GPU function; never called
        return None
except ImportError:
    pass
'''


def space_folder(folder, snapshot: dict) -> list:
    """A folder Hugging Face can run as a Gradio Space: the desk brief's app, from the snapshot.

    Inputs: folder, a new folder (created if missing); snapshot, from desk_snapshot.
    Output: the files written, as Paths: app.py (the ZeroGPU placeholder, then the app built by gradio_app from the
    snapshot and launched, which on a Space is how it starts), README.md (the Space's YAML header, every version
    in quotes, then the disclaimer), requirements.txt (no gradio: the Space installs Gradio from sdk_version),
    desk_snapshot.json, and deploykit.py and bondmath.py, copied unchanged.
    Convention: the YAML header is sdk gradio, sdk_version GRADIO_SDK_VERSION, python_version SPACE_PYTHON (the
    ZeroGPU page's rule, read on the build day), app_file app.py.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    header = (f'---\ntitle: PFI Desk Brief\ncolorFrom: green\ncolorTo: blue\nsdk: gradio\nsdk_version: '
              f'"{GRADIO_SDK_VERSION}"\npython_version: "{SPACE_PYTHON}"\napp_file: app.py\npinned: false\n'
              f"short_description: A descriptive desk brief from saved runs, as of {snapshot['as_of']}\n---\n")
    files = {
        "app.py": ('"""The desk brief on a Hugging Face Space: the Gradio app of deploykit, from the snapshot."""\n'
                   + SPACE_PLACEHOLDER + "\nimport json\nfrom pathlib import Path\n\nimport deploykit\n\n"
                   'snapshot = json.loads(Path("desk_snapshot.json").read_text(encoding="utf-8"))\n'
                   "demo = deploykit.gradio_app(snapshot)\ndemo.launch()\n"),
        "README.md": (header + "\n# PFI desk brief\n\nThe Course 8 desk brief, served from a snapshot of saved runs: "
                      f"every figure is as of {snapshot['as_of']} in the course's files. It refuses any request for "
                      "a view, and it holds no key.\n\n" + DISCLAIMER + "\n"),
        "requirements.txt": "# Gradio comes from sdk_version in README.md; the app needs nothing else\n",
        "desk_snapshot.json": json.dumps(snapshot, indent=1, sort_keys=True) + "\n",
    }
    written = []
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")
        written.append(folder / name)
    for module in (Path(__file__), Path(bondmath.__file__)):
        written.append(Path(shutil.copy(module, folder / module.name)))
    return sorted(written, key=lambda path: path.name)


def _yaml_header(readme_text: str) -> dict:
    """The YAML header of a Space's README.md (between the first two --- lines), read by yaml.safe_load."""
    import yaml

    parts = readme_text.split("---\n")
    if len(parts) < 3 or parts[0].strip():
        raise ValueError("README.md does not start with a --- YAML header")
    return yaml.safe_load(parts[1])


def check_space_folder(folder) -> list[str]:
    """The problems of a Space folder, each as a sentence; empty means none found.

    Input: folder, from space_folder.
    Output: one sentence per problem: sdk_version or python_version read as a number by YAML (write them in
    quotes); gradio listed in requirements.txt (the Space installs it from sdk_version); app.py without the
    @spaces.GPU placeholder (ZeroGPU refuses it); and every problem check_deploy_folder finds but the entrypoint
    rule (a Space runs app_file, not an app variable).
    """
    folder = Path(folder)
    problems = []
    header = _yaml_header((folder / "README.md").read_text(encoding="utf-8"))
    for key in ("sdk_version", "python_version"):
        if not isinstance(header.get(key), str):
            problems.append(f"README.md: {key} {header.get(key)!r} is not text; write it in quotes")
    requirements = folder / "requirements.txt"
    lines = requirements.read_text(encoding="utf-8").splitlines() if requirements.is_file() else []
    if any(_normal(re.split(r"[=<>!~ ;\[]", line.strip(), maxsplit=1)[0]) == "gradio" for line in lines
           if line.strip() and not line.strip().startswith("#")):
        problems.append("requirements.txt: gradio is listed; the Space installs it from sdk_version")
    if "@spaces.GPU" not in (folder / "app.py").read_text(encoding="utf-8"):
        problems.append("app.py: no @spaces.GPU function; a ZeroGPU Space refuses the app")
    problems += [p for p in check_deploy_folder(folder) if not p.startswith("no entrypoint defines app")]
    return problems


def space_status(runtime) -> str:
    """One line on a Space's state: for a live-deploy cell only.

    Input: runtime, what huggingface_hub.HfApi().get_space_runtime(space_id) returned (its stage and hardware).
    Output: for example "Space stage RUNNING on zero-a10g." or "Space stage SLEEPING on zero-a10g.".
    """
    return f"Space stage {runtime.stage} on {runtime.hardware}."


_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)


def dockerfile_text(python_tag: str, requirements: str, module: str) -> str:
    """The course's Dockerfile for the bond service: one image that runs the same on every machine.

    Inputs: python_tag, the exact tag of the official Python image (for example "3.13-slim", or the full
    3.13.x-slim tag read on the build day); requirements, the requirements file to install; module, the module that
    defines app (app for app.py).
    Output: the Dockerfile's text: FROM python:<tag>, WORKDIR /app, the requirements copied and installed first
    (so a code change does not reinstall them), the named files copied (never COPY . .), a user that is not root,
    EXPOSE 8000, and CMD in exec form running uvicorn on the port the platform gives in PORT, else 8000.
    Convention: the RUN and CMD lines run in a Linux shell inside the image; you type only docker commands.
    """
    return f"""FROM python:{python_tag}
WORKDIR /app
COPY {requirements} .
RUN python -m pip install --no-cache-dir -r {requirements}
COPY {module}.py bondmath.py deploykit.py ./
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn {module}:app --host 0.0.0.0 --port ${{PORT:-8000}}"]
"""


def dockerignore_text() -> str:
    """The course's .dockerignore: what never goes into an image, whatever a COPY line says."""
    return "\n".join([".env", ".env.*", "!.env.example", ".git", "cache/", "__pycache__/", "*.db", "*.log",
                      "*.xlsx", ".pytest_cache/"]) + "\n"


def check_dockerfile(dockerfile: str, dockerignore: str) -> list[str]:
    """The problems of a Dockerfile and its .dockerignore that would still build and run; empty means none found.

    Inputs: dockerfile and dockerignore, the two files' texts (dockerignore "" when there is none).
    Output: one sentence per problem: a FROM image with no tag or the tag latest; an ENV or ARG line that gives a
    value to a name like a secret (KEY, TOKEN, SECRET, PASSWORD), which every copy of the image would carry; COPY .
    or ADD . while .dockerignore does not exclude .env files; no USER line (the server would run as root); a CMD in
    shell form rather than exec form (["...", "..."]).
    """
    problems = []
    lines = [line.strip() for line in dockerfile.splitlines() if line.strip() and not line.strip().startswith("#")]
    ignored = {line.strip() for line in dockerignore.splitlines()}
    for line in lines:
        word, _, rest = line.partition(" ")
        word = word.upper()
        if word == "FROM":
            image = rest.split()[0]
            if ":" not in image.split("/")[-1] or image.endswith(":latest"):
                problems.append(f"{line}: pin the image to a tag, never latest or none")
        if word in ("ENV", "ARG") and _SECRET_NAME.search(rest.split("=")[0]) and "=" in rest and rest.split("=", 1)[1]:
            problems.append(f"{word} {rest.split('=')[0]}: a secret's value in the image; set it on the platform")
        if word in ("COPY", "ADD") and rest.split()[0] == "." and not {".env", ".env*", ".env.*"} & ignored:
            problems.append(f"{line}: copies the whole folder, and .dockerignore does not exclude .env files")
        if word == "CMD" and not rest.startswith("["):
            problems.append(f"{line}: CMD in shell form; write it in exec form, a JSON list")
    if not any(line.upper().startswith("USER ") for line in lines):
        problems.append("no USER line: the server runs as root inside the container")
    return problems


import itertools  # a request counter
from datetime import datetime, timedelta, timezone

LOG_COLUMNS = ["time_utc", "request_id", "path", "status", "latency_ms", "bytes_out", "refused"]


def fake_clock(start: str, step_ms: float):
    """A deterministic clock for notebooks and tests, so every run prints the same log.

    Inputs: start, the first wall-clock time in UTC as ISO text ("2026-10-02T14:00:00"); step_ms, how far each
    reading moves, in milliseconds.
    Output: (wall, perf): wall() returns a UTC datetime, start first, then step_ms later at each reading; perf()
    returns seconds, 0.0 first, then step_ms / 1000 more at each reading. A request read twice by perf takes exactly
    step_ms.
    """
    first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    walls, perfs = itertools.count(), itertools.count()

    def wall() -> datetime:
        return first + timedelta(milliseconds=next(walls) * step_ms)

    def perf() -> float:
        return next(perfs) * step_ms / 1000

    return wall, perf


def _stamp(moment: datetime) -> str:
    """A UTC time as the log writes it: ISO 8601 with milliseconds and Z."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def log_middleware(app, sink, clock=None, wall=None):
    """Log every request the app answers: one JSON line each, with the request-log columns and nothing else.

    Inputs: app, a FastAPI app; sink, a function given each line (a file append on your machine, print on a
    platform, whose logs keep what a function prints); clock, a perf-counter function in seconds (by default
    time.perf_counter); wall, a function returning the UTC time (by default the real clock).
    Output: the same app, with the middleware added.
    Convention: a line holds time_utc, request_id (16 hexadecimal characters), path, status, latency_ms (1 decimal),
    bytes_out (the response's content-length), and refused (the X-Desk-Refused header). Never a query value, a
    request body, a header's value, or the client's address: a log is not a second copy of the requests.
    """
    clock = clock or time.perf_counter
    wall = wall or (lambda: datetime.now(timezone.utc))
    counter = itertools.count(1)

    @app.middleware("http")
    async def log_request(request, call_next):
        started, when = clock(), wall()
        response = await call_next(request)
        latency_ms = (clock() - started) * 1000
        number = next(counter)
        line = {"time_utc": _stamp(when),
                "request_id": hashlib.sha256(f"{_stamp(when)}:{number}".encode("ascii")).hexdigest()[:16],
                "path": request.url.path, "status": response.status_code, "latency_ms": round(latency_ms, 1),
                "bytes_out": int(response.headers.get("content-length", 0)),
                "refused": response.headers.get("X-Desk-Refused") == "true"}
        sink(json.dumps(line))
        return response

    return app


def read_log(path_or_lines):
    """A request log as a typed table, from the course's CSV, a JSON-lines file, or a list of JSON lines.

    Input: path_or_lines, a .csv path (data/course9_request_log.csv), a path of JSON lines (what log_middleware's
    sink wrote), or a list of those lines.
    Output: a DataFrame with LOG_COLUMNS: time_utc as a UTC timestamp, status and bytes_out as integers, latency_ms
    as a float, refused as True or False, sorted by time.
    """
    import pandas as pd

    if isinstance(path_or_lines, (str, Path)) and Path(path_or_lines).suffix == ".csv":
        frame = pd.read_csv(path_or_lines)
    else:
        lines = (Path(path_or_lines).read_text(encoding="utf-8").splitlines()
                 if isinstance(path_or_lines, (str, Path)) else list(path_or_lines))
        frame = pd.DataFrame([json.loads(line) for line in lines if line.strip()], columns=LOG_COLUMNS)
    frame = frame[LOG_COLUMNS].copy()
    frame["time_utc"] = pd.to_datetime(frame["time_utc"], utc=True, format="ISO8601")
    frame = frame.astype({"status": "int64", "bytes_out": "int64", "latency_ms": "float64"})
    frame["refused"] = frame["refused"].map(lambda value: value is True or str(value).lower() == "true")
    return frame.sort_values("time_utc", kind="stable", ignore_index=True)


def log_summary(frame, by="path"):
    """Requests, errors, refusals, and latency, by path (or any column of the log).

    Inputs: frame, from read_log; by, the column to group by.
    Output: a DataFrame indexed by the groups with columns requests, errors_4xx, errors_5xx, refused, p50_ms,
    p95_ms, mean_ms.
    Convention: percentiles are linear between the closest ranks (NumPy's and pandas' default, Excel's
    PERCENTILE.INC), in milliseconds.
    """
    grouped = frame.groupby(by)
    summary = grouped.agg(requests=("status", "size"),
                          errors_4xx=("status", lambda s: int(((s >= 400) & (s < 500)).sum())),
                          errors_5xx=("status", lambda s: int((s >= 500).sum())),
                          refused=("refused", "sum"),
                          p50_ms=("latency_ms", lambda s: s.quantile(0.50)),
                          p95_ms=("latency_ms", lambda s: s.quantile(0.95)),
                          mean_ms=("latency_ms", "mean"))
    return summary.astype({"refused": "int64"})


def health_report(frame, p95_limit_ms: float, error_limit: float) -> dict:
    """Each UTC day of a log against two limits: is the day ok, or an alert?

    Inputs: frame, from read_log (filter it to one path first to watch that path); p95_limit_ms, the most p95
    latency allowed, in ms; error_limit, the largest share of requests allowed to end in an error (status 400 or
    above), from 0 to 1.
    Output: {"YYYY-MM-DD": {"requests", "p95_ms", "error_share", "status"}} for each day, in date order, status
    "alert" when the day's p95 is over p95_limit_ms or its error share is over error_limit, else "ok".
    """
    report = {}
    for day, rows in frame.groupby(frame["time_utc"].dt.strftime("%Y-%m-%d")):
        p95 = float(rows["latency_ms"].quantile(0.95))
        share = float((rows["status"] >= 400).mean())
        report[day] = {"requests": len(rows), "p95_ms": p95, "error_share": share,
                       "status": "alert" if p95 > p95_limit_ms or share > error_limit else "ok"}
    return report


import platform  # the Python version on a model card


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_model(model, folder, card: dict) -> dict:
    """Save a fitted model and its card: the file, its SHA-256, and what it was fitted on.

    Inputs: model, a fitted scikit-learn model; folder, where to write (created if missing); card, what you know
    about it: features, target, training window, rows.
    Output: the card as written to model_card.json: your fields, plus file ("model.joblib"), sha256 (of that
    file), and versions (Python, scikit-learn, joblib, numpy), so the file can be checked and the environment
    matched before it is loaded.
    Convention: the model file is never committed (a joblib file runs code when loaded); the card is.
    """
    import joblib

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, folder / "model.joblib")
    versions = {"python": platform.python_version()} | {
        name: importlib.metadata.version(name) for name in ("scikit-learn", "joblib", "numpy")}
    written = dict(card) | {"file": "model.joblib", "sha256": _sha256(folder / "model.joblib"), "versions": versions}
    (folder / "model_card.json").write_text(json.dumps(written, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                            newline="\n")
    return written


def load_model(folder):
    """Load a model saved by save_model, after checking the file is the one its card describes.

    Input: folder, holding model.joblib and model_card.json.
    Output: the fitted model.
    Raises ValueError when the file's SHA-256 differs from the card's: the file changed after it was saved.
    Never load a joblib or pickle file someone else made: loading one runs whatever code it holds (joblib's own
    documentation says so). The check here proves the file is yours, unchanged; it does not make a stranger's safe.
    """
    import joblib

    folder = Path(folder)
    card = json.loads((folder / "model_card.json").read_text(encoding="utf-8"))
    if _sha256(folder / card["file"]) != card["sha256"]:
        raise ValueError(f"{card['file']} is not the file its card describes: its SHA-256 differs; do not load it")
    return joblib.load(folder / card["file"])


def drift_table(train, recent, features):
    """How far the inputs a model now receives sit from the rows it was fitted on, feature by feature.

    Inputs: train, the training rows; recent, the rows arriving as requests; features, the columns to compare.
    Output: a DataFrame indexed by feature with columns train_mean, train_std, train_min, train_max (all from the
    training rows only), recent_mean, z (the recent mean's distance from the training mean in training standard
    deviations, (recent_mean - train_mean) / train_std), and outside_share (the share of recent rows below the
    training minimum or above the training maximum, from 0 to 1).
    Convention: std with ddof 1 (Excel's STDEV.S). The reference statistics come from the training rows alone: mixing
    in the recent rows pulls the reference toward them and hides the drift.
    """
    import pandas as pd

    rows = {}
    for feature in features:
        reference, now = train[feature], recent[feature]
        mean, std = reference.mean(), reference.std(ddof=1)
        rows[feature] = {"train_mean": mean, "train_std": std, "train_min": reference.min(),
                         "train_max": reference.max(), "recent_mean": now.mean(), "z": (now.mean() - mean) / std,
                         "outside_share": float(((now < reference.min()) | (now > reference.max())).mean())}
    return pd.DataFrame.from_dict(rows, orient="index")


def drift_flags(table, z_limit: float = 2.0, outside_limit: float = 0.05):
    """The drift table with a flag per feature, and the rule that set it.

    Inputs: table, from drift_table; z_limit, the largest absolute z allowed; outside_limit, the largest share of
    recent rows allowed outside the training range.
    Output: a copy of the table with a column flag (True when |z| > z_limit or outside_share > outside_limit); the
    rule in words is in the result's attrs["rule"].
    Convention: a flag says the inputs left the training window. It does not say why they moved, or what the model
    would return next.
    """
    flagged = table.copy()
    flagged["flag"] = (flagged["z"].abs() > z_limit) | (flagged["outside_share"] > outside_limit)
    flagged.attrs["rule"] = (f"flag when |z| > {z_limit:g} or more than {outside_limit:.0%} of recent rows are "
                             "outside the training range")
    return flagged


# Course 8's model prices (agentkit.PRICES), US dollars per token as text: gpt-4.1-mini, standard tier,
# https://developers.openai.com/api/docs/pricing (read 2026-10-08)
PRICES = {"gpt-4.1-mini": {"prompt": "0.0000004", "completion": "0.0000016", "read": "2026-10-08"}}
# what each free tier includes in a month, with the page and the date it was read; the day 14 builder re-reads each
# page and replaces these figures with that day's reading
INCLUDED = {
    "requests": {"included": 1_000_000, "page": "vercel.com/docs/plans/hobby", "read": "2026-10-12",
                 "what": "Vercel Hobby function invocations a month"},
    "transfer_gb": {"included": 100, "page": "vercel.com/docs/plans/hobby", "read": "2026-10-12",
                    "what": "Vercel Hobby fast data transfer a month, in GB"},
    "duration_hours": {"included": 4, "page": "vercel.com/docs/plans/hobby", "read": "2026-10-12",
                       "what": "Vercel Hobby CPU hours a month (the log's latency summed, an upper bound)"},
}
_GETTERS = ("getenv", "get_secret")


def secret_names(folder):
    """Every secret name a folder's Python files read, against the names its .env.example lists.

    Input: folder, a deploy folder or a repo.
    Output: a DataFrame with columns name, used_in (the files, comma-separated), in_example (True when
    .env.example lists it), one row per name read by os.environ["NAME"], os.environ.get("NAME"), os.getenv("NAME"),
    or get_secret("NAME", ...), in name order.
    Convention: reads names from the code with ast, never a value from anywhere.
    """
    import pandas as pd

    folder = Path(folder)
    used = {}
    for path in _files(folder):
        if path.suffix != ".py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            name = None
            if isinstance(node, ast.Subscript) and ast.unparse(node.value).endswith("environ"):
                name = node.slice
            elif isinstance(node, ast.Call) and node.args:
                called = ast.unparse(node.func)
                if called.endswith("environ.get") or called.split(".")[-1] in _GETTERS:
                    name = node.args[0]
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                used.setdefault(name.value, set()).add(path.relative_to(folder).as_posix())
    example = folder / ".env.example"
    listed = ({line.split("=", 1)[0].strip() for line in example.read_text(encoding="utf-8").splitlines()
               if "=" in line and not line.lstrip().startswith("#")} if example.is_file() else set())
    rows = [{"name": name, "used_in": ", ".join(sorted(files)), "in_example": name in listed}
            for name, files in sorted(used.items())]
    return pd.DataFrame(rows, columns=["name", "used_in", "in_example"])


def env_example(names) -> str:
    """The text of a .env.example: one NAME= line per secret name, sorted, never a value."""
    return "".join(f"{name}=\n" for name in sorted(set(names)))


def cost_meter(log, usage_per_request: dict, prices: dict, included: dict):
    """What a month of requests uses, against what each free tier includes, and what a live desk's model would cost.

    Inputs: log, from read_log; usage_per_request, {path: {"prompt_tokens": n, "completion_tokens": m}}, the average
    tokens a live request to that path would send (from the saved runs' usage; an empty dict in replay, which sends
    none); prices, {"prompt": dollars per token as text, "completion": ...} (a value of PRICES); included,
    {measure: {"included": amount, ...}} (INCLUDED).
    Output: a DataFrame, one row per month and measure, with columns month, measure, used, included, status. The
    measures: requests; transfer_gb (bytes_out summed, in GB of 1024^3 bytes); duration_hours (latency_ms summed,
    in hours); model_usd (requests by path times the tokens a request sends times the price). status is "within" or
    "over" the included amount, and "no free tier" for model_usd.
    """
    import pandas as pd

    rows = []
    for month, rows_of_month in log.groupby(log["time_utc"].dt.strftime("%Y-%m")):
        used = {"requests": float(len(rows_of_month)),
                "transfer_gb": float(rows_of_month["bytes_out"].sum()) / 1024 ** 3,
                "duration_hours": float(rows_of_month["latency_ms"].sum()) / 3_600_000}
        model_usd = 0.0
        for path, count in rows_of_month["path"].value_counts().items():
            tokens = usage_per_request.get(path, {})
            model_usd += count * (tokens.get("prompt_tokens", 0) * float(prices["prompt"])
                                  + tokens.get("completion_tokens", 0) * float(prices["completion"]))
        for measure, value in used.items():
            limit = included[measure]["included"]
            rows.append({"month": month, "measure": measure, "used": value, "included": limit,
                         "status": "over" if value > limit else "within"})
        rows.append({"month": month, "measure": "model_usd", "used": model_usd, "included": None,
                     "status": "no free tier"})
    return pd.DataFrame(rows, columns=["month", "measure", "used", "included", "status"])


def daily_cap(app, max_requests: int, wall=None):
    """Refuse requests over a daily cap with HTTP 429, so a public URL cannot run up a bill.

    Inputs: app, a FastAPI app; max_requests, the requests answered in one UTC day; wall, a function returning the
    UTC time (a fake clock in tests; by default the real clock).
    Output: the same app. Request number max_requests + 1 of a UTC day, and every one after it that day, gets 429
    with {"detail": the cap, the day, and when it resets}.
    Convention: the count lives in one process. A serverless platform runs many processes at once and starts new
    ones, so on a platform the cap is a floor on what is answered, not a guarantee.
    """
    from fastapi.responses import JSONResponse

    wall = wall or (lambda: datetime.now(timezone.utc))
    counts = {}

    @app.middleware("http")
    async def cap(request, call_next):
        day = wall().astimezone(timezone.utc).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
        if counts[day] > max_requests:
            return JSONResponse(status_code=429, content={
                "detail": f"daily cap of {max_requests} requests reached for {day} UTC; it resets at 00:00 UTC"})
        return await call_next(request)

    return app
