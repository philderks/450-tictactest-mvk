"""Pure release-change classification tests; no repository access required."""
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "release_changes.py"
spec = importlib.util.spec_from_file_location("release_changes", MODULE)
assert spec is not None and spec.loader is not None
release_changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_changes)


class VersionOnlyChangeTests(unittest.TestCase):
    def test_pure_project_version_bump(self):
        before = "plugins { id 'java' }\nversion = '1.2.0'\n// retained comment\n"
        after = before.replace("'1.2.0'", "'1.3.0'")
        self.assertTrue(release_changes.version_only_change(before, after, "1.2.0", "1.3.0"))

    def test_double_quoted_project_version_bump_preserves_all_other_bytes(self):
        for ending in ("\n", "\r\n", ""):
            before = 'version = "1.2.0"' + ending
            after = 'version = "1.3.0"' + ending
            with self.subTest(ending=ending):
                self.assertTrue(release_changes.version_only_change(before, after, "1.2.0", "1.3.0"))
                self.assertFalse(release_changes.version_only_change(
                    before, after.replace('"', "'"), "1.2.0", "1.3.0"))

    def test_extra_functional_change_is_not_exempt(self):
        before = "version = '1.2.0'\nsourceCompatibility = 17\n"
        after = "version = '1.3.0'\nsourceCompatibility = 21\n"
        self.assertFalse(release_changes.version_only_change(before, after, "1.2.0", "1.3.0"))

    def test_exactly_one_canonical_standalone_assignment_is_required(self):
        invalid = [
            "version = '1.2.0'\nversion = '1.2.0'\n",
            "// no project assignment: 1.2.0\n",
            " version = '1.2.0'\n",
            "version='1.2.0'\n",
            "version = '1.2.0' // comment\n",
            "version = '01.2.0'\n",
            "version = '1.2'\n",
            "version = '1.2.0-SNAPSHOT'\n",
        ]
        for before in invalid:
            with self.subTest(before=before):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("1.2.0", "1.3.0"), "1.2.0", "1.3.0"))

    def test_values_must_match_requested_canonical_versions(self):
        before = "version = '1.2.0'\n"
        after = "version = '1.3.0'\n"
        for previous, target in [("1.1.0", "1.3.0"), ("1.2.0", "1.4.0"),
                                 ("01.2.0", "1.3.0"), ("1.2.0", "1.3.0-SNAPSHOT")]:
            with self.subTest(previous=previous, target=target):
                self.assertFalse(release_changes.version_only_change(before, after, previous, target))

    def test_malformed_or_ambiguous_additional_assignment_is_not_exempt(self):
        extras = ["version='9.9.9'\n", " version = '9.9.9'\n", "version = value\n",
                  "project.version = '9.9.9'\n", "apply plugin: 'java'; version = '9.9.9'\n",
                  "version '9.9.9'\n"]
        for extra in extras:
            before = "version = '1.2.0'\n" + extra
            with self.subTest(extra=extra):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("'1.2.0'", "'1.3.0'"), "1.2.0", "1.3.0"))

    def test_indexed_or_reflective_project_writes_force_backend(self):
        extras = [
            "project['version'] = '9.9.9'\n",
            'this["version"] = "9.9.9"\n',
            "(project)['version'] = '9.9.9'\n",
            "project.setProperty('version', '9.9.9')\n",
            "this.setProperty('version', '9.9.9')\n",
            "setProperty('version', '9.9.9')\n",
            "project.putAt('version', '9.9.9')\n",
            "project.'version' = '9.9.9'\n",
            'this."version" = "9.9.9"\n',
            "project.\"${'version'}\" = '9.9.9'\n",
            "project.properties['version'] = '9.9.9'\n",
            "this.metaClass.setProperty(this, 'version', '9.9.9')\n",
            "def owner = project; owner.setVersion('9.9.9')\n",
        ]
        for extra in extras:
            before = "version = '1.2.0'\n" + extra
            after = before.replace("version = '1.2.0'", "version = '1.3.0'")
            with self.subTest(extra=extra):
                exempt = release_changes.version_only_change(before, after, "1.2.0", "1.3.0")
                self.assertFalse(exempt)
                result = release_changes.classify_changes(
                    [{"status": "M", "path": "build.gradle"}], version_only_build=exempt)
                self.assertEqual(result["components"], "backend")
                self.assertEqual(result["metadata_paths"], [])

    def test_implicit_project_reflection_or_property_maps_are_not_exempt(self):
        extras = [
            "properties['version'] = '9.9.9'\n",
            "getProperties()['version'] = '9.9.9'\n",
            "invokeMethod('setVersion', ['9.9.9'])\n",
            "getMetaClass().setAttribute(thisObject, 'version', '9.9.9')\n",
            "getProject()['version'] = '9.9.9'\n",
            "binding.setVariable('version', '9.9.9')\n",
        ]
        for extra in extras:
            before = "version = '1.2.0'\n" + extra
            with self.subTest(extra=extra):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("version = '1.2.0'", "version = '1.3.0'"),
                    "1.2.0", "1.3.0"))

    def test_slashy_literal_version_text_without_project_assignment_is_not_exempt(self):
        for prefix, suffix in [("def example = /\n", "/\n"),
                               ("def example = $/\n", "/$\n")]:
            before = prefix + "version = '1.2.0'\n" + suffix
            with self.subTest(prefix=prefix):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("1.2.0", "1.3.0"), "1.2.0", "1.3.0"))

    def test_unindented_assignment_in_groovy_scope_is_not_top_level(self):
        for prefix, suffix in [
            ("dependencies {\n", "}\n"),
            ("ext {\n", "}\n"),
            ("allprojects {\n", "}\n"),
            ("subprojects {\n", "}\n"),
            ("def configure() {\n", "}\n"),
            ("def configure = {\n", "}\n"),
            ("if (false) {\n", "}\n"),
            ("def example = [\n", "]\n"),
        ]:
            before = prefix + "version = '1.2.0'\n" + suffix
            with self.subTest(prefix=prefix):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("1.2.0", "1.3.0"), "1.2.0", "1.3.0"))

    def test_interpolated_string_can_hide_project_writes(self):
        extras = [
            'def rendered = "${setProperty(\'version\', \'9.9.9\')}"\n',
            'def rendered = """\n${project.setVersion(\'9.9.9\')}\n"""\n',
            'def rendered = "${version = \'9.9.9\'}"\n',
        ]
        for extra in extras:
            before = "version = '1.2.0'\n" + extra
            with self.subTest(extra=extra):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("version = '1.2.0'", "version = '1.3.0'"),
                    "1.2.0", "1.3.0"))

    def test_unterminated_literal_or_escape_is_not_provable(self):
        extras = ['def unfinished = "\n', "def unfinished = '\n",
                  'def unfinished = """\n', "def unfinished = '''\n",
                  'def invalid = "line one\nline two"\n',
                  "def invalid = 'line one\nline two'\n",
                  "\\u0076ersion = '9.9.9'\n"]
        for extra in extras:
            before = "version = '1.2.0'\n" + extra
            with self.subTest(extra=extra):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("version = '1.2.0'", "version = '1.3.0'"),
                    "1.2.0", "1.3.0"))

    def test_control_flow_or_local_binding_cannot_prove_project_assignment(self):
        prefixes = ["if (false)\n", "while (false)\n", "return\n",
                    "def version\n", "String version\n", "Object version\n"]
        for prefix in prefixes:
            before = prefix + "version = '1.2.0'\n"
            with self.subTest(prefix=prefix):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("1.2.0", "1.3.0"), "1.2.0", "1.3.0"))

    def test_assignment_inside_multiline_comment_or_string_is_not_project_assignment(self):
        for wrapper in [("/*\n", "*/\n"), ("def text = '''\n", "'''\n")]:
            before = wrapper[0] + "version = '1.2.0'\n" + wrapper[1]
            with self.subTest(wrapper=wrapper):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("1.2.0", "1.3.0"), "1.2.0", "1.3.0"))

    def test_inline_or_multiline_ambiguous_version_writes_are_not_exempt(self):
        for extra in ["println 'x'; version += '-local'\n", "println 'x'; version\n = '9.9.9'\n",
                      "setVersion('9.9.9')\n", "project.setVersion('9.9.9')\n"]:
            before = "version = '1.2.0'\n" + extra
            with self.subTest(extra=extra):
                self.assertFalse(release_changes.version_only_change(
                    before, before.replace("'1.2.0'", "'1.3.0'"), "1.2.0", "1.3.0"))

    def test_unchanged_commented_or_quoted_version_text_is_not_an_assignment(self):
        before = ("// version = '6.0.0'\n/*\nversion = '7.0.0'\n*/\n"
                  "def example = '''\nversion = '8.0.0'\n'''\n"
                  "version = '1.2.0'\n// Groovy comment remains byte-for-byte\n")
        self.assertTrue(release_changes.version_only_change(
            before, before.replace("version = '1.2.0'", "version = '1.3.0'"), "1.2.0", "1.3.0"))

    def test_static_build_dsl_and_manifest_project_reads_remain_exempt(self):
        before = (
            "plugins {\n id 'example' version '1.2.0'\n}\n"
            "// project['version'] = '8.0.0'; ${notCode} {\n"
            "/* this.setProperty('version', '9.9.9') } */\n"
            "version = '1.2.0'\n"
            "dependencies {\n implementation 'example:version:1.2.0'\n}\n"
            "def example = '''\nversion = '5.0.0'\n'''\n"
            'def description = """Static version documentation { }"""\n'
            "jar {\n manifest {\n attributes(\n"
            "  'Implementation-Title': project.name,\n"
            "  'Implementation-Version': project.version\n"
            " )\n }\n}\n"
        )
        for quote in ("'", '"'):
            for ending in ("\n", "\r\n"):
                old = before.replace("\nversion = '1.2.0'", "\nversion = " + quote + "1.2.0" + quote)
                old = old.replace("\n", ending)
                after = old.replace("version = " + quote + "1.2.0" + quote,
                                    "version = " + quote + "1.3.0" + quote)
                with self.subTest(quote=quote, ending=ending):
                    self.assertTrue(release_changes.version_only_change(old, after, "1.2.0", "1.3.0"))

    def test_non_string_inputs_are_not_exempt(self):
        valid = ["version = '1.2.0'\n", "version = '1.3.0'\n", "1.2.0", "1.3.0"]
        for index in range(4):
            for invalid in [None, 1, b"1.2.0"]:
                args = list(valid)
                args[index] = invalid
                with self.subTest(index=index, invalid=invalid):
                    self.assertFalse(release_changes.version_only_change(*args))

    def test_every_other_byte_is_significant(self):
        for quote in ("'", '"'):
            old_assignment = "version = " + quote + "1.2.0" + quote
            new_assignment = "version = " + quote + "1.3.0" + quote
            before = "plugins { id 'example' version '1.2.0' }\n" + old_assignment + "\n// unchanged\n"
            valid_after = before.replace(old_assignment, new_assignment)
            self.assertTrue(release_changes.version_only_change(before, valid_after, "1.2.0", "1.3.0"))
            other_quote = '"' if quote == "'" else "'"
            invalid_after = [valid_after + "\n", valid_after.rstrip("\n"),
                             valid_after.replace("\n", "\r\n"),
                             valid_after.replace("// unchanged", "// changed"),
                             valid_after.replace("'example' version '1.2.0'", "'example' version '1.3.0'"),
                             valid_after.replace(new_assignment, new_assignment.replace(" = ", "= ")),
                             valid_after.replace(new_assignment, " " + new_assignment),
                             valid_after.replace(new_assignment, new_assignment + " // note"),
                             valid_after.replace(new_assignment, "version = " + other_quote + "1.3.0" + other_quote),
                             valid_after.replace("plugins { id 'example' version '1.2.0' }\n", "")]
            for after in invalid_after:
                with self.subTest(quote=quote, after=after):
                    self.assertFalse(release_changes.version_only_change(before, after, "1.2.0", "1.3.0"))
            crlf_before = before.replace("\n", "\r\n")
            self.assertTrue(release_changes.version_only_change(
                crlf_before, valid_after.replace("\n", "\r\n"), "1.2.0", "1.3.0"))


class ClassifyChangesTests(unittest.TestCase):
    def assert_paths(self, paths, category, **kwargs):
        result = release_changes.classify_changes([{"status": "M", "path": path} for path in paths], **kwargs)
        self.assertEqual(result, {
            "backend": category in ("backend", "both"),
            "frontend": category in ("frontend", "both"),
            "components": category if category in ("backend", "frontend", "both") else "none",
            "changed_paths": sorted(set(paths)),
            "operational_paths": sorted(set(paths)) if category == "operational" else [],
            "metadata_paths": sorted(set(paths)) if category == "metadata" else [],
        })

    def test_backend_build_runtime_paths(self):
        paths = ["scripts/start-console.sh", "scripts/backend-version.py",
                 "scripts/serve-backend-version.py", "scripts/runtime-README.md",
                 "build.gradle", "settings.gradle", "gradle.properties", "gradlew", "gradlew.bat",
                 "gradle/wrapper/gradle-wrapper.properties", ".devcontainer/devcontainer.json"]
        for path in paths:
            with self.subTest(path=path):
                self.assert_paths([path], "backend")

    def test_release_packaging_paths_select_both(self):
        for path in ["scripts/package-web-release.py", ".github/workflows/release.yml"]:
            with self.subTest(path=path):
                self.assert_paths([path], "both")

    def test_documentation_repository_metadata_paths_do_not_deploy(self):
        paths = ["docs/release.md", "README.md", "CHANGELOG.md", "RELEASE.md", "LICENSE", "LICENSE.md",
                 ".gitignore", ".gitattributes", ".editorconfig", ".github/ISSUE_TEMPLATE/bug.md",
                 ".github/PULL_REQUEST_TEMPLATE/feature.md", ".github/pull_request_template.md",
                 ".github/dependabot.yml"]
        self.assert_paths(paths, "metadata")

    def test_tests_and_exact_ci_workflows_are_metadata(self):
        paths = ["src/test/java/AppTest.java", "src/e2eTest/java/WebTest.java",
                 "scripts/tests/test_release_changes.py", "infra/tests/validate.sh",
                 ".github/scripts/coverage.py", ".github/workflows/ci.yml",
                 ".github/workflows/coverage-gate.yml", ".github/workflows/devcontainer.yml"]
        self.assert_paths(paths, "metadata")

    def test_operational_paths_are_separate_from_application_and_metadata(self):
        paths = ["infra/main.tf", "infra/environments/example/README.md",
                 "scripts/plan-release-deploy.py", "scripts/release_changes.py",
                 ".github/workflows/deploy.yml"]
        self.assert_paths(paths, "operational")
        result = release_changes.classify_changes([
            {"status": "M", "path": "infra/tests/validate.sh"},
            {"status": "M", "path": "infra/main.tf"},
        ])
        self.assertEqual(result["metadata_paths"], ["infra/tests/validate.sh"])
        self.assertEqual(result["operational_paths"], ["infra/main.tf"])
        self.assertEqual(result["components"], "none")

    def test_only_build_gradle_is_exempt_when_version_only(self):
        self.assert_paths(["build.gradle"], "metadata", version_only_build=True)
        self.assert_paths(["build.gradle"], "backend", version_only_build=False)
        self.assert_paths(["settings.gradle", "scripts/backend-version.py"], "backend", version_only_build=True)
        result = release_changes.classify_changes([
            {"status": "M", "path": "build.gradle"}, {"status": "M", "path": "src/main/App.java"},
            {"status": "M", "path": "frontend/app.js"}], version_only_build=True)
        self.assertEqual(result["components"], "both")
        self.assertEqual(result["metadata_paths"], ["build.gradle"])

    def test_unknown_paths_fail_closed_even_alongside_known_changes(self):
        for path in ["unknown.txt", "scripts/unknown.py", ".github/workflows/new.yml",
                     "src/mainish/App.java", "frontends/app.js", "gradlew.extra",
                     ".github/workflows/ci.yml.extra", ".github/workflows/coverage-gate.yaml",
                     ".github/unknown.md", "README.rst", "frontend", "docs"]:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    release_changes.classify_changes([
                        {"status": "M", "path": "frontend/app.js"}, {"status": "M", "path": path}])

    def test_rename_and_copy_classify_both_sides(self):
        for status in ["R100", "R0", "C75", "C100"]:
            with self.subTest(status=status):
                result = release_changes.classify_changes([
                    {"status": status, "old_path": "frontend/old.js", "path": "src/main/New.java"}])
                self.assertEqual(result, {
                    "backend": True, "frontend": True, "components": "both",
                    "changed_paths": ["frontend/old.js", "src/main/New.java"],
                    "operational_paths": [], "metadata_paths": [],
                })
        result = release_changes.classify_changes([
            {"status": "R88", "old_path": "infra/main.tf", "path": "docs/main.tf"}])
        self.assertEqual(result["components"], "none")
        self.assertEqual(result["metadata_paths"], ["docs/main.tf"])
        self.assertEqual(result["operational_paths"], ["infra/main.tf"])
        with self.assertRaises(ValueError):
            release_changes.classify_changes([
                {"status": "C100", "old_path": "unknown.py", "path": "frontend/app.js"}])

    def test_statuses_are_limited_to_supported_git_name_status_records(self):
        for status in ["A", "M", "D", "T"]:
            with self.subTest(status=status):
                self.assertEqual(release_changes.classify_changes([
                    {"status": status, "path": "frontend/app.js"}])["components"], "frontend")
        for kind in ("R", "C"):
            for score in range(101):
                for suffix in (str(score), "{:03d}".format(score)):
                    with self.subTest(status=kind + suffix):
                        self.assertEqual(release_changes.classify_changes([
                            {"status": kind + suffix, "old_path": "README.md", "path": "frontend/app.js"}
                        ])["components"], "frontend")
        for status in ["U", "UU", "AA", "X", "B", "?", "", " M", "M100", "R", "C", "R101",
                       "C999", "R-1", "R1.0", "R+1", "R1000", "C١", "R1\n"]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    release_changes.classify_changes([
                        {"status": status, "path": "frontend/app.js", "old_path": "frontend/old.js"}])

    def test_malformed_change_records_raise_value_error(self):
        malformed = [None, "", [], {}, {"path": "frontend/app.js"}, {"status": "M"},
                     {"status": None, "path": "frontend/app.js"},
                     {"status": 1, "path": "frontend/app.js"},
                     {"status": [], "path": "frontend/app.js"},
                     {"status": "R100", "path": "frontend/app.js"},
                     {"status": "C50", "old_path": "frontend/old.js"},
                     {"status": "M", "path": "frontend/app.js", "old_path": "README.md"},
                     {"status": "M", "path": "frontend/app.js", "typo": True}]
        for change in malformed:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    release_changes.classify_changes([change])
        for changes in (None, {}, (), "", 1, iter([])):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    release_changes.classify_changes(changes)
        for flag in (None, 0, 1, "true", [], {}):
            with self.subTest(flag=flag):
                with self.assertRaises(ValueError):
                    release_changes.classify_changes([], version_only_build=flag)

    def test_paths_are_validated_without_normalizing_filenames(self):
        invalid = [None, 1, [], {}, b"frontend/app.js", "", "/frontend/app.js",
                   "./frontend/app.js", "frontend/./app.js", "frontend/../app.js",
                   "frontend//app.js", "frontend/app.js/", "frontend/", "frontend/..",
                   "frontend/\\app.js", "frontend/app\x00.js", "C:/frontend/app.js"]
        for path in invalid:
            with self.subTest(path=path):
                for record in [{"status": "M", "path": path},
                               {"status": "R100", "old_path": path, "path": "frontend/app.js"},
                               {"status": "C100", "old_path": "README.md", "path": path}]:
                    with self.assertRaises(ValueError):
                        release_changes.classify_changes([record])

    def test_filenames_with_spaces_newlines_and_unicode_remain_exact(self):
        self.assert_paths(["frontend/ leading and trailing .js ", "frontend/line\nfeed.js",
                           "frontend/Grüße_日本語.js", "frontend/quote'\".js", "frontend/tab\tfile.js"], "frontend")

    def test_results_are_sorted_unique_complete_and_do_not_mutate_input(self):
        changes = [
            {"status": "M", "path": "infra/z.tf"},
            {"status": "R100", "old_path": "frontend/old.js", "path": "src/main/New.java"},
            {"status": "D", "path": "README.md"},
            {"status": "C050", "old_path": "docs/a.md", "path": "infra/a.tf"},
            {"status": "A", "path": "frontend/old.js"},
            {"status": "M", "path": "docs/a.md"},
        ]
        original = [dict(change) for change in changes]
        expected = {
            "backend": True, "frontend": True, "components": "both",
            "changed_paths": ["README.md", "docs/a.md", "frontend/old.js", "infra/a.tf", "infra/z.tf", "src/main/New.java"],
            "metadata_paths": ["README.md", "docs/a.md"],
            "operational_paths": ["infra/a.tf", "infra/z.tf"],
        }
        self.assertEqual(release_changes.classify_changes(changes), expected)
        self.assertEqual(release_changes.classify_changes(list(reversed(changes))), expected)
        self.assertEqual(changes, original)

    def test_empty_changes_have_complete_none_result(self):
        self.assertTrue(hasattr(release_changes, "classify_changes"))
        self.assertEqual(release_changes.classify_changes([]), {
            "backend": False, "frontend": False, "components": "none",
            "changed_paths": [], "operational_paths": [], "metadata_paths": [],
        })

    def test_application_source_paths_select_components(self):
        for paths, components in [(["src/main/java/App.java"], "backend"),
                                  (["frontend/app.js"], "frontend"),
                                  (["frontend/app.js", "src/main/resources/app.yml"], "both")]:
            with self.subTest(paths=paths):
                result = release_changes.classify_changes([{"status": "M", "path": path} for path in paths])
                self.assertEqual(result, {
                    "backend": components in ("backend", "both"),
                    "frontend": components in ("frontend", "both"), "components": components,
                    "changed_paths": sorted(paths), "operational_paths": [], "metadata_paths": [],
                })


if __name__ == "__main__":
    unittest.main()
