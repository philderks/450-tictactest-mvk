"""Pure, fail-closed release change classification.

The version-only exception is a bounded lexical recognizer for this repository's
static Gradle style, not a Groovy parser or evaluator. It accepts one exact,
unindented, standalone ``version = 'X.Y.Z'`` or ``version = "X.Y.Z"`` assignment
at delimiter depth zero; only the version value may change. Normal comments,
static quoted strings, plugin/dependency versions and the JAR manifest's
``project.name``/``project.version`` reads remain supported.

Explicit project/this access other than those reads, known reflection/property-map
forms, control-flow/type scopes and recognized local version bindings are not
exempt. Neither are double-quoted strings containing dollars, unmasked slashes
(including division), escapes, leftover quotes or unbalanced delimiters. These
deliberate false negatives select the backend build. This does not resolve
Gradle plugins, external scripts, arbitrary method semantics or all possible
Groovy metaprogramming; it must not be used as a general Groovy semantic validator.
"""


import re


_VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_ASSIGNMENT = re.compile(
    r"^version = (?P<quote>['\"])(?P<value>" + _VERSION + r")(?P=quote)\r?$", re.MULTILINE
)
_NON_CODE = re.compile(
    r"//[^\r\n]*|/\*[\s\S]*?\*/|'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\""
    r"|'(?:\\.|[^'\\\r\n])*'|\"(?:\\.|[^\"\\\r\n])*\""
)
_PROJECT_VERSION = re.compile(
    r"^[ \t]*(?:(?:project|this)[ \t]*\.[ \t]*)?version\b"
    r"|(?<![\w$])version\s*(?=(?:[+*/-]?=)|\()"
    r"|(?<![\w$])setVersion\s*(?=\()", re.MULTILINE
)


_UNSUPPORTED_PROJECT_ACCESS = re.compile(
    r"(?<![\w$])(?:this\b|project\b(?![ \t]*\.[ \t]*(?:name|version)[ \t]*(?=[,\r\n)]|$)))"
    r"|(?<![\w$])(?:setProperty|putAt|metaClass|getMetaClass|invokeMethod|binding|"
    r"properties|getProperties|getProject)\b"
)


_UNSUPPORTED_SCOPE = re.compile(
    r"(?<![\w$])(?:if|else|for|while|switch|try|catch|finally|return|throw|class|trait|interface|enum)\b"
    r"|(?<![\w$])(?:def|String|Object)[ \t\r\n]+version\b"
)


def _project_assignment(text: str):
    # GStrings can execute writes inside interpolation. Reject all dollar signs
    # in double-quoted literals (even escaped ones) instead of interpreting them.
    if any(match.group().startswith('"') and "$" in match.group()
           for match in _NON_CODE.finditer(text)):
        return None
    # Mask literals/comments without changing offsets or line endings.
    code = _NON_CODE.sub(lambda m: re.sub(r"[^\r\n]", " ", m.group()), text)
    # Leftover quotes/escapes mean that the bounded literal masker cannot
    # establish which characters are code. An unmasked slash is also ambiguous
    # (slashy/dollar-slashy string versus division); choose the backend path.
    if any(character in code for character in "/'\"\\"):
        return None
    # Indexed/dynamic/reflective access and aliases are not provable metadata.
    # Keep ordinary project.name/project.version reads used by the JAR manifest.
    if _UNSUPPORTED_PROJECT_ACCESS.search(code) or _UNSUPPORTED_SCOPE.search(code):
        return None
    matches = [match for match in _ASSIGNMENT.finditer(text)
               if code[match.start():match.start() + len("version")] == "version"]
    if len(matches) != 1:
        return None
    # Delimiter depth, not indentation, determines whether this is top-level.
    # This is deliberately only a lexical check, not Groovy scope evaluation.
    stack = []
    pairs = {"}": "{", ")": "(", "]": "["}
    for offset, character in enumerate(code):
        if offset == matches[0].start() and stack:
            return None
        if character in "{([":
            stack.append(character)
        elif character in pairs:
            if not stack or stack.pop() != pairs[character]:
                return None
    if stack:
        return None
    candidates = list(_PROJECT_VERSION.finditer(code))
    if len(candidates) != 1 or candidates[0].start() != matches[0].start():
        return None
    return matches[0]


def version_only_change(before: str, after: str, previous_version: str, target_version: str) -> bool:
    """True only when the sole edit replaces the exact project version value."""
    if not all(isinstance(value, str) for value in (before, after, previous_version, target_version)):
        return False
    old = _project_assignment(before)
    new = _project_assignment(after)
    if old is None or new is None:
        return False
    if old.group("value") != previous_version or new.group("value") != target_version:
        return False
    start, end = old.span("value")
    return before[:start] + target_version + before[end:] == after


_BACKEND_PATHS = {
    "scripts/start-console.sh", "scripts/backend-version.py",
    "scripts/serve-backend-version.py", "scripts/runtime-README.md",
    "build.gradle", "settings.gradle", "gradle.properties", "gradlew", "gradlew.bat",
}


_METADATA_PATHS = {
    "README.md", "CHANGELOG.md", "RELEASE.md", "LICENSE", "LICENSE.md",
    ".gitignore", ".gitattributes", ".editorconfig",
    ".github/pull_request_template.md", ".github/dependabot.yml",
    ".github/workflows/ci.yml", ".github/workflows/coverage-gate.yml",
    ".github/workflows/devcontainer.yml",
}
_METADATA_PREFIXES = (
    "docs/", ".github/ISSUE_TEMPLATE/", ".github/PULL_REQUEST_TEMPLATE/",
    "src/test/", "src/e2eTest/", "scripts/tests/", "infra/tests/", ".github/scripts/",
)


_BOTH_PATHS = {"scripts/package-web-release.py", ".github/workflows/release.yml"}
_OPERATIONAL_PATHS = {
    "scripts/plan-release-deploy.py", "scripts/release_changes.py", ".github/workflows/deploy.yml",
}


def _path_category(path: str, version_only_build: bool) -> str:
    if path == "build.gradle" and version_only_build:
        return "metadata"
    if path in _BACKEND_PATHS or path.startswith(("src/main/", "gradle/", ".devcontainer/")):
        return "backend"
    if path.startswith("frontend/"):
        return "frontend"
    if path in _BOTH_PATHS:
        return "both"
    if path in _METADATA_PATHS or path.startswith(_METADATA_PREFIXES):
        return "metadata"
    if path in _OPERATIONAL_PATHS or path.startswith("infra/"):
        return "operational"
    raise ValueError("Unknown release path: {!r}".format(path))


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("Change paths must be nonempty, unambiguous strings")
    if re.match(r"[A-Za-z]:", path) or any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("Change paths must be repository-relative without empty or dot segments: {!r}".format(path))


def classify_changes(changes: list, version_only_build: bool = False) -> dict:
    """Classify explicit changed paths without accessing Git or the filesystem."""
    if not isinstance(changes, list) or not isinstance(version_only_build, bool):
        raise ValueError("changes must be a list and version_only_build must be a bool")
    paths = set()
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("status"), str):
            raise ValueError("Each change must be a dict with a string status")
        status = change["status"]
        scored = re.fullmatch(r"[RC][0-9]{1,3}", status)
        if status not in ("A", "M", "D", "T") and not (scored and int(status[1:]) <= 100):
            raise ValueError("Unsupported change status: {!r}".format(status))
        expected_keys = {"status", "path", "old_path"} if scored else {"status", "path"}
        if set(change) != expected_keys:
            raise ValueError("Malformed fields for change status {!r}".format(status))
        for field in ("path", "old_path") if scored else ("path",):
            _validate_path(change[field])
            paths.add(change[field])
    paths = sorted(paths)
    categories = {path: _path_category(path, version_only_build) for path in paths}
    backend = any(category in ("backend", "both") for category in categories.values())
    frontend = any(category in ("frontend", "both") for category in categories.values())
    components = "both" if backend and frontend else "backend" if backend else "frontend" if frontend else "none"
    return {
        "backend": backend, "frontend": frontend, "components": components,
        "changed_paths": paths,
        "operational_paths": [path for path in paths if categories[path] == "operational"],
        "metadata_paths": [path for path in paths if categories[path] == "metadata"],
    }
