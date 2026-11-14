"""Offline regressions; no credentials, live API calls, or workload mutations."""

import contextlib
import copy
import io
import json
import os
import pathlib
import shlex
import tempfile
import unittest
import warnings
from unittest.mock import patch

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "skills/dibufusion-api/scripts"))
import dibu


class LoginTests(unittest.TestCase):
    def test_expired_auth_suggests_manual_login_without_prompting(self):
        failure = dibu.urllib.error.HTTPError("http://fixture", 401, "fixture", {}, io.BytesIO(b"fixture-token"))
        with patch("urllib.request.build_opener") as opener, patch("builtins.input") as prompt:
            opener.return_value.open.side_effect = failure
            with self.assertRaises(ValueError) as error:
                dibu.request("http://fixture", "Token fixture-token", {"method": "GET"}, "/", {}, None, {})
            self.assertIn(dibu.login_command(), str(error.exception))
            self.assertNotIn("fixture-token", str(error.exception))
            opener.return_value.open.assert_called_once()
            prompt.assert_not_called()

    def test_new_user_login_creates_cache_without_previous_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            home = pathlib.Path(directory)
            with (
                patch("builtins.input", return_value="fixture-user"),
                patch.object(dibu.getpass, "getpass", return_value="fixture-password"),
                patch.object(dibu.pathlib.Path, "home", return_value=home),
                patch.object(dibu, "auth_config", side_effect=AssertionError("Must not read old auth")),
                patch("urllib.request.build_opener") as opener,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
                    b'{"token":"fixture-token"}'
                )
                dibu.login()
            target = home / ".cache" / "dibu_token"
            self.assertEqual(target.read_text().strip(), "fixture-token")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_interactive_login_posts_without_auth_and_saves_private_token(self):
        with tempfile.TemporaryDirectory() as directory:
            home = pathlib.Path(directory)
            target = home / ".cache" / "dibu_token"
            target.parent.mkdir()
            target.write_text("fixture-old-token")
            target.chmod(0o644)
            out = io.StringIO()
            with (
                patch("sys.argv", ["dibu", "login"]),
                patch("builtins.input", return_value=" fixture-user "),
                patch.object(dibu.getpass, "getpass", return_value="fixture-password"),
                patch.object(dibu.pathlib.Path, "home", return_value=home),
                patch.dict(os.environ, {"DIBU_BASE_URL": "http://fixture-site/"}),
                patch("urllib.request.build_opener") as opener,
                contextlib.redirect_stdout(out),
            ):
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
                    b'{"token":"fixture-new-token","email":"fixture@example.test"}'
                )
                dibu.main()
                req = opener.return_value.open.call_args.args[0]
                self.assertEqual(req.full_url, "http://fixture-site/user/login/")
                self.assertEqual(req.get_method(), "POST")
                self.assertEqual(json.loads(req.data), {"username": "fixture-user", "password": "fixture-password"})
                self.assertIsNone(req.get_header("Authorization"))
                self.assertIsNone(req.get_header("Cookie"))
                self.assertEqual(req.get_header("Referer"), "http://fixture-site/login?redirect=/dashboard")
                self.assertEqual(dibu.auth_config()[1], "Token fixture-new-token")
            self.assertEqual(target.read_text().strip(), "fixture-new-token")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(target.parent.iterdir()), [target])
            for secret in ("fixture-new-token", "fixture-password", "fixture@example.test"):
                self.assertNotIn(secret, out.getvalue())

    def test_invalid_login_responses_do_not_overwrite_existing_token(self):
        for response in (
            b"invalid JSON",
            b"[]",
            b"{}",
            b'{"token":""}',
            b'{"token":"contains space"}',
            b'{"token":123}',
            b'{"token":"fixture-token","error":"fixture-password"}',
            b'{"token":"bad\\u0000token"}',
        ):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                home = pathlib.Path(directory)
                target = home / ".cache" / "dibu_token"
                target.parent.mkdir()
                target.write_text("fixture-old-token")
                with (
                    patch("builtins.input", return_value="fixture-user"),
                    patch.object(dibu.getpass, "getpass", return_value="fixture-password"),
                    patch.object(dibu.pathlib.Path, "home", return_value=home),
                    patch("urllib.request.build_opener") as opener,
                ):
                    opener.return_value.open.return_value.__enter__.return_value.read.return_value = response
                    with self.assertRaises(ValueError) as error:
                        dibu.login()
                self.assertEqual(target.read_text(), "fixture-old-token")
                self.assertNotIn("fixture-password", str(error.exception))

    def test_login_http_and_network_errors_preserve_token_without_echoing_server(self):
        errors = [
            dibu.urllib.error.HTTPError("http://fixture", 401, "fixture", {}, io.BytesIO(b"fixture-password")),
            dibu.urllib.error.URLError("fixture-password"),
        ]
        for failure in errors:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as directory:
                home = pathlib.Path(directory)
                target = home / ".cache" / "dibu_token"
                target.parent.mkdir()
                target.write_text("fixture-old-token")
                with (
                    patch("builtins.input", return_value="fixture-user"),
                    patch.object(dibu.getpass, "getpass", return_value="fixture-password"),
                    patch.object(dibu.pathlib.Path, "home", return_value=home),
                    patch("urllib.request.build_opener") as opener,
                ):
                    opener.return_value.open.side_effect = failure
                    with self.assertRaises(ValueError) as error:
                        dibu.login()
                    opener.return_value.open.assert_called_once()
                self.assertNotIn("fixture-password", str(error.exception))
                self.assertEqual(target.read_text(), "fixture-old-token")

    def test_atomic_save_failure_keeps_old_token_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            home = pathlib.Path(directory)
            target = home / ".cache" / "dibu_token"
            target.parent.mkdir()
            target.write_text("fixture-old-token")
            with (
                patch("builtins.input", return_value="fixture-user"),
                patch.object(dibu.getpass, "getpass", return_value="fixture-password"),
                patch.object(dibu.pathlib.Path, "home", return_value=home),
                patch("urllib.request.build_opener") as opener,
                patch.object(dibu.os, "replace", side_effect=OSError("fixture write failed")),
            ):
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
                    b'{"token":"fixture-token"}'
                )
                with self.assertRaises(OSError):
                    dibu.login()
            self.assertEqual(target.read_text(), "fixture-old-token")
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_login_cancellation_or_echo_fallback_never_sends_credentials(self):
        def echo_warning(*args):
            warnings.warn("fixture echo fallback", dibu.getpass.GetPassWarning)

        for failure in (EOFError(), KeyboardInterrupt(), echo_warning):
            with (
                patch("builtins.input", return_value="fixture-user"),
                patch.object(dibu.getpass, "getpass", side_effect=failure),
                patch("urllib.request.build_opener") as opener,
            ):
                with self.assertRaisesRegex(ValueError, "cancelled"):
                    dibu.login()
                opener.assert_not_called()

    def test_missing_or_invalid_auth_gives_manual_login_command(self):
        with tempfile.TemporaryDirectory() as directory:
            home = pathlib.Path(directory)
            target = home / ".cache" / "dibu_token"
            target.parent.mkdir()
            for token in (None, "", "contains space"):
                if token is not None:
                    target.write_text(token)
                with (
                    patch.object(dibu.pathlib.Path, "home", return_value=home),
                    patch("builtins.input") as prompt,
                    patch.object(dibu.getpass, "getpass") as password,
                ):
                    with self.assertRaises(ValueError) as error:
                        dibu.auth_config()
                    self.assertIn(dibu.login_command(), str(error.exception))
                    prompt.assert_not_called()
                    password.assert_not_called()

    def test_login_help_is_offline_and_credentials_cannot_be_command_flags(self):
        with (
            patch("sys.argv", ["dibu", "login", "--help"]),
            patch("builtins.input") as prompt,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as error:
                dibu.main()
            self.assertEqual(error.exception.code, 0)
            prompt.assert_not_called()
        for flags in (["--password", "fixture"], ["--username", "fixture"], ["-v"], ["--execute"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                dibu.parse_cli(["login", *flags])


class DibuTests(unittest.TestCase):
    def test_account_private_fields_require_explicit_reveal_even_raw_and_output(self):
        private = {key: "fixture-" + key for key in ("nickname", "grade", "email", "gender", "phone")}
        response = {"user_id": 1, "username": "fixture-user", **private, "future_field": "preserve"}
        for reveal in (False, True):
            for mode in ([], ["-v"], ["--output"]):
                with self.subTest(reveal=reveal, mode=mode), tempfile.TemporaryDirectory() as directory:
                    target = pathlib.Path(directory) / "profile.json"
                    flags = ["--show-private"] if reveal else []
                    flags += mode + ([str(target)] if mode == ["--output"] else [])
                    out = io.StringIO()
                    with (
                        patch("sys.argv", ["dibu", "account", *flags]),
                        patch.object(dibu, "auth_config", return_value=("http://fixture", "Token fixture")),
                        patch("urllib.request.build_opener") as opener,
                        contextlib.redirect_stdout(out),
                    ):
                        reply = opener.return_value.open.return_value.__enter__.return_value
                        reply.read.return_value = json.dumps(response).encode()
                        reply.status = 200
                        dibu.main()
                        request = opener.return_value.open.call_args.args[0]
                        self.assertNotIn("show_private", request.full_url)
                    result = json.loads(target.read_text() if mode == ["--output"] else out.getvalue())
                    for key, actual in private.items():
                        self.assertEqual(result[key], actual if reveal else "*")
                        if not reveal:
                            self.assertNotIn(actual, out.getvalue())
                    self.assertEqual(result["username"], "fixture-user")
                    self.assertEqual(result["future_field"], "preserve")
                    if target.exists():
                        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_private_flag_is_local_and_masking_does_not_change_original(self):
        args, params = dibu.parse_cli(["account", "profile", "--show-private"])
        self.assertTrue(args.alias_show_private)
        self.assertEqual(params, {})
        original = {"data": {"email": None, "nickname": "fixture"}, "items": [{"phone": "fixture"}]}
        snapshot = copy.deepcopy(original)
        masked = dibu.mask_profile(original)
        self.assertEqual(masked["data"], {"email": "*", "nickname": "*"})
        self.assertEqual(masked["items"][0]["phone"], "*")
        self.assertEqual(original, snapshot)

    def test_non_json_private_profile_is_not_displayed_or_saved(self):
        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.build_opener") as opener:
            target = pathlib.Path(directory) / "profile.json"
            reply = opener.return_value.open.return_value.__enter__.return_value
            reply.read.return_value = b"fixture-private-non-json"
            reply.status = 200
            with self.assertRaisesRegex(ValueError, "not valid JSON") as error:
                dibu.request(
                    "http://fixture",
                    "Token fixture",
                    {"method": "GET"},
                    "/",
                    {},
                    None,
                    {},
                    str(target),
                    mask_private=True,
                )
            self.assertNotIn("fixture-private", str(error.exception))
            self.assertFalse(target.exists())

    def test_profile_http_errors_also_mask_private_fields(self):
        failure = dibu.urllib.error.HTTPError(
            "http://fixture", 403, "fixture", {}, io.BytesIO(b'{"email":"fixture-email","code":"permission_denied"}')
        )
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = failure
            with self.assertRaises(ValueError) as error:
                dibu.request("http://fixture", "Token fixture", {"method": "GET"}, "/", {}, None, {}, mask_private=True)
        self.assertNotIn("fixture-email", str(error.exception))
        self.assertIn("permission_denied", str(error.exception))

    def test_distributed_group_replaces_jobs_in_public_help_and_preserves_legacy(self):
        self.assertIn("distributed", dibu.COMMAND_GROUPS)
        self.assertNotIn("jobs", dibu.COMMAND_GROUPS)
        for action, operation in dibu.COMMAND_GROUPS["distributed"][1].items():
            current, params = dibu.parse_cli(["distributed", action])
            legacy, legacy_params = dibu.parse_cli(["jobs", action])
            self.assertEqual(current.operation, operation)
            self.assertEqual(legacy.operation, operation)
            self.assertEqual(params, legacy_params)
            self.assertTrue(dibu.canonical_command(operation).startswith("distributed "))
        for command in ("distributed", "jobs"):
            args, params = dibu.parse_cli(["-v", command, "list", "--state", "pending"])
            self.assertEqual(args.operation, "jobs")
            self.assertTrue(args.raw)
            self.assertEqual(params, {"operate_id": 2})
            args, _ = dibu.parse_cli([command])
            self.assertEqual(args.operation, "jobs")

    def test_resources_default_ready_only_all_and_raw(self):
        dashboard = {
            "stale": True,
            "sampled_at_ms": 100,
            "errors": {"fixture": "stale"},
            "nodes": [
                {"node_id": 1, "node_status": "Ready", "gpu_remain_num": 2},
                {"node_id": 2, "node_status": "SchedulingDisabled", "gpu_remain_num": 8},
            ],
        }
        for flags in ([], ["--all"], ["-v"]):
            out = io.StringIO()
            with (
                patch("sys.argv", ["dibu", "resources", *flags]),
                patch.object(dibu, "auth_config", return_value=("fixture", "fixture")),
                patch.object(dibu, "request", return_value=dashboard),
                contextlib.redirect_stdout(out),
            ):
                dibu.main()
            result = json.loads(out.getvalue())
            if flags == ["-v"]:
                self.assertEqual(result, dashboard)
            else:
                self.assertEqual([x["node_id"] for x in result["nodes"]], [1, 2] if flags else [1])
                self.assertTrue(result["dashboard_stale"])
                self.assertEqual(result["dashboard_errors"], dashboard["errors"])
                self.assertTrue(all(x["schedulable_free_gpus"] is None for x in result["nodes"]))
        self.assertEqual(dibu.resource_summary({"nodes": [], "stale": False})["nodes"], [])

    def test_workload_display_omits_dra_and_reduces_timing_without_mutating_raw(self):
        row = {
            "container_id": 1,
            "status": "Running",
            "num_gpu": 2,
            "timing": {"state": "running", "elapsed_seconds": 10, "remaining_seconds": 590},
            "dra_request": {
                "parameters": {"count": 2, "memory_mib": 4096},
                "future_diagnostic": "available in raw output",
            },
        }
        response = {"count": 1, "next": "fixture-page2", "results": [row]}
        original = copy.deepcopy(response)
        for operation in ("tasks", "experiments"):
            result = dibu.compact_response(operation, response)
            after = result["results"][0]
            self.assertNotIn("dra_request", after)
            self.assertEqual(after["timing"], {"state": "running"})
            self.assertEqual(after["status"], "Running")
            self.assertEqual(after["num_gpu"], 2)
            self.assertEqual(result["next"], "fixture-page2")
        self.assertEqual(response, original)

    def test_grouped_commands_match_legacy_requests(self):
        cases = [
            (
                ["images", "note", "--id", "42", "--note", "fixture"],
                ["image-note", "--id", "42", "--note", "fixture"],
            ),
            (
                ["files", "list", "--shared", "--path", "/fixture"],
                ["shared-files", "--path", "/fixture"],
            ),
            (["files", "space", "--refresh"], ["file-space-refresh"]),
            (["workloads", "delete", "--id", "42"], ["container-delete", "--id", "42"]),
            (["billing", "usage", "--limit", "50"], ["usage", "--limit", "50"]),
            (["jobs", "logs", "--id", "42"], ["job-log", "--id", "42"]),
        ]
        for grouped, legacy in cases:
            with self.subTest(grouped=grouped):
                a, params = dibu.parse_cli(grouped)
                b, old_params = dibu.parse_cli(legacy)
                self.assertEqual(a.operation, b.operation)
                self.assertEqual(
                    dibu.prepare(a.operation, params, None),
                    dibu.prepare(b.operation, old_params, None),
                )

    def test_grouped_global_options_keep_order_and_duplicates(self):
        args, params = dibu.parse_cli(["--param", "page=2", "-v", "tasks", "list", "--param", "size=3"])
        self.assertEqual(args.operation, "tasks")
        self.assertTrue(args.raw)
        self.assertEqual(params, {"page": 2, "size": 3})
        args, params = dibu.parse_cli(["--raw", "tasks", "summary", "--id", "42"])
        self.assertEqual(args.operation, "task-summary")
        self.assertEqual(params, {"container_id": 42})

    def test_grouped_writes_stay_previews_without_authentication(self):
        for argv, method in (
            (["files", "space", "--refresh"], "PATCH"),
            (["images", "note", "--id", "42", "--note", "fixture"], "GET"),
            (["workloads", "delete", "--id", "42"], "DELETE"),
        ):
            out = io.StringIO()
            with (
                self.subTest(argv=argv),
                patch("sys.argv", ["dibu", *argv]),
                patch.object(dibu, "auth_config") as auth,
                patch.object(dibu, "request") as request,
                contextlib.redirect_stdout(out),
            ):
                dibu.main()
                self.assertTrue(json.loads(out.getvalue())["preview"])
                self.assertEqual(json.loads(out.getvalue())["method"], method)
                auth.assert_not_called()
                request.assert_not_called()

    def test_group_help_is_offline_and_shared_writes_are_rejected(self):
        for group in dibu.COMMAND_GROUPS:
            with (
                self.subTest(group=group),
                patch("sys.argv", ["dibu", group, "--help"]),
                patch.object(dibu, "auth_config") as auth,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as error:
                    dibu.main()
                self.assertEqual(error.exception.code, 0)
                auth.assert_not_called()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            dibu.parse_cli(["files", "remove", "--shared", "--path", "/fixture"])
        with self.assertRaisesRegex(ValueError, "Unknown action"):
            dibu.parse_cli(["images", "invalid-action"])

    def test_deduplicated_task_inspection_matches_legacy_status(self):
        response = {
            "results": [{"container_id": 42, "status": "Running"}],
            "next": None,
        }
        with (
            patch.object(dibu, "auth_config", return_value=("fixture", "fixture")),
            patch.object(dibu, "request", return_value=response),
        ):
            current = dibu.run_summary("task-summary", {"container_id": 42})
            legacy = dibu.run_summary("task-status", {"container_id": 42})
        self.assertEqual(current, legacy)

    def test_billing_page_sizes_match_live_confirmed_values(self):
        for operation in ("usage", "ledger"):
            for size in (20, 50, 100):
                _, params = dibu.parse_cli([operation, "--limit", str(size)])
                self.assertEqual(dibu.prepare(operation, params, None)[2]["size"], size)
            for size in (2, 10, 21, 200):
                with (
                    self.subTest(operation=operation, size=size),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    dibu.parse_cli([operation, "--limit", str(size)])
            _, params = dibu.parse_cli([operation, "--param", "size=10"])
            self.assertEqual(params["size"], 10)

    def test_output_preserves_business_error_response_and_still_fails(self):
        response = b'{"error":{"code":"fixture_failure","message":"rejected"}}'
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "error.json"
            for use_output in (False, True):
                with (
                    self.subTest(output=use_output),
                    patch("urllib.request.build_opener") as opener,
                ):
                    reply = opener.return_value.open.return_value.__enter__.return_value
                    reply.read.return_value = response
                    reply.status = 200
                    with self.assertRaisesRegex(ValueError, "fixture_failure"):
                        dibu.request(
                            "http://fixture",
                            "Token fixture",
                            {"method": "GET"},
                            "/",
                            {},
                            None,
                            {},
                            str(target) if use_output else None,
                        )
            self.assertEqual(target.read_bytes(), response)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_cli_output_business_error_emits_no_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "error.json"
            out = io.StringIO()
            with (
                patch("sys.argv", ["dibu", "credits", "--output", str(target)]),
                patch.object(
                    dibu,
                    "auth_config",
                    return_value=("http://fixture", "Token fixture"),
                ),
                patch("urllib.request.build_opener") as opener,
                contextlib.redirect_stdout(out),
            ):
                reply = opener.return_value.open.return_value.__enter__.return_value
                reply.read.return_value = b'{"error":{"code":"fixture_failure"}}'
                reply.status = 200
                with self.assertRaisesRegex(ValueError, "fixture_failure"):
                    dibu.main()
            self.assertEqual(out.getvalue(), "")
            self.assertTrue(target.exists())

    def test_output_still_supports_non_json_logs_and_empty_responses(self):
        for response in (b"fixture log\n", b"", b"\xff\x00"):
            with (
                self.subTest(response=response),
                tempfile.TemporaryDirectory() as directory,
                patch("urllib.request.build_opener") as opener,
            ):
                target = pathlib.Path(directory) / "response"
                reply = opener.return_value.open.return_value.__enter__.return_value
                reply.read.return_value = response
                reply.status = 200
                result = dibu.request(
                    "http://fixture",
                    "Token fixture",
                    {"method": "GET"},
                    "/",
                    {},
                    None,
                    {},
                    str(target),
                )
                self.assertEqual(target.read_bytes(), response)
                self.assertEqual(result["bytes"], len(response))

    def test_header_normalization_deduplicates_same_values_and_matches_wire(self):
        headers = dibu.parse_headers(
            [
                " Idempotency-Key : fixture-key ",
                "idempotency-key:fixture-key",
                "x-dibufusion-estimate-fingerprint:fixture-quote",
            ]
        )
        self.assertEqual(
            headers,
            {
                "Idempotency-Key": "fixture-key",
                "X-DibuFusion-Estimate-Fingerprint": "fixture-quote",
            },
        )
        request = dibu.urllib.request.Request("http://fixture", headers=headers)
        self.assertEqual(request.get_header("Idempotency-key"), "fixture-key")

    def test_invalid_headers_fail_before_authentication_even_for_previews(self):
        for entries in (
            ["Idempotency-Key:fixture-A", "idempotency-key:fixture-B"],
            ["Idempotency-Key:fixture-A", "idempotency-key:"],
            ["Idempotency-Key:  "],
            ["Idempotency-Key:a\nb"],
            ["Authorization:fixture"],
            ["malformed"],
        ):
            argv = ["dibu", "image-delete", "--id", "42"]
            for entry in entries:
                argv += ["--header", entry]
            with (
                self.subTest(entries=entries),
                patch("sys.argv", argv),
                patch.object(dibu, "auth_config") as auth,
                patch.object(dibu, "request") as request,
            ):
                with self.assertRaises(ValueError):
                    dibu.main()
                auth.assert_not_called()
                request.assert_not_called()

    def test_body_templates_are_offline_and_leave_password_empty(self):
        operations = (
            "container-create",
            "container-convert",
            "job-create",
            "estimate",
            "extension-estimate",
            "extension-submit",
        )
        for operation in operations:
            out = io.StringIO()
            with (
                self.subTest(operation=operation),
                patch("sys.argv", ["dibu", operation, "--template"]),
                patch.object(dibu, "auth_config") as auth,
                patch.object(dibu, "request") as request,
                contextlib.redirect_stdout(out),
            ):
                dibu.main()
                body = json.loads(out.getvalue())
                self.assertTrue(set(dibu.CAT[operation]["body_schema"]["required"]).issubset(body))
                auth.assert_not_called()
                request.assert_not_called()
            if operation in ("container-create", "container-convert"):
                self.assertEqual(body["password"], "")
                with self.assertRaisesRegex(ValueError, "password"):
                    dibu.prepare(operation, {}, body)

    def test_template_cannot_accidentally_execute_or_save_a_response(self):
        for extra in (
            ["--execute"],
            ["--output", "fixture.json"],
            ["--describe"],
            ["--param", "cpu=2"],
            ["--cpu", "2"],
            ["--dry-run"],
        ):
            with (
                self.subTest(extra=extra),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                dibu.parse_cli(["container-create", "--template", *extra])
        with (
            patch("sys.argv", ["dibu", "tasks", "--template"]),
            self.assertRaisesRegex(ValueError, "No body template"),
        ):
            dibu.main()

    def test_named_list_options_match_legacy_api_parameters(self):
        _, named = dibu.parse_cli(["tasks", "--state", "pending", "--limit", "20", "--page", "2"])
        _, legacy = dibu.parse_cli(
            [
                "tasks",
                "--param",
                "operate_id=2",
                "--param",
                "size=20",
                "--param",
                "page=2",
            ]
        )
        self.assertEqual(dibu.prepare("tasks", named, None), dibu.prepare("tasks", legacy, None))
        _, params = dibu.parse_cli(["images", "--scope", "mine", "--temporary", "true", "-q", "ubuntu"])
        self.assertEqual(params, {"opt": 1, "is_temporary": 1, "q": "ubuntu"})

    def test_legacy_global_options_work_before_and_after_operation(self):
        args, params = dibu.parse_cli(["--param", "page=2", "-v", "tasks", "--param", "size=3"])
        self.assertEqual(params, {"page": 2, "size": 3})
        self.assertTrue(args.raw)
        args, _ = dibu.parse_cli(
            [
                "--header",
                "Idempotency-Key:a",
                "container-create",
                "--header",
                "X-DibuFusion-Estimate-Fingerprint:b",
            ]
        )
        self.assertEqual(len(args.header), 2)

    def test_invalid_or_conflicting_options_fail_without_network(self):
        cases = [
            ["tasks", "--limit", "0"],
            ["tasks", "--state", "invalid"],
            ["profile", "--id", "42"],
            ["tasks", "--state", "pending", "--param", "operate_id=1"],
            ["tasks", "--param", "page=1", "--param", "page=2"],
            ["container-create", "--duration", "0h"],
            ["image-delete", "--id", "-1"],
        ]
        for argv in cases:
            with (
                self.subTest(argv=argv),
                patch.object(dibu, "request") as request,
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                dibu.parse_cli(argv)
            request.assert_not_called()

    def test_operation_help_and_schema_need_no_authentication(self):
        for name in {**dibu.SUMMARY_OPS, **dibu.CAT}:
            for flag in ("--help", "--describe"):
                out = io.StringIO()
                with (
                    self.subTest(operation=name, flag=flag),
                    patch("sys.argv", ["dibu", name, flag]),
                    patch.object(
                        dibu,
                        "auth_config",
                        side_effect=AssertionError("No authentication expected"),
                    ),
                    patch.object(dibu, "request") as request,
                    contextlib.redirect_stdout(out),
                ):
                    if flag == "--help":
                        with self.assertRaises(SystemExit) as error:
                            dibu.main()
                        self.assertEqual(error.exception.code, 0)
                    else:
                        dibu.main()
                        self.assertEqual(json.loads(out.getvalue())["operation"], name)
                request.assert_not_called()

    def test_all_catalog_examples_parse(self):
        for name, spec in {**dibu.SUMMARY_OPS, **dibu.CAT}.items():
            for example in spec["cli"]["examples"]:
                with self.subTest(operation=name, example=example):
                    args, _ = dibu.parse_cli(shlex.split(example))
                    self.assertEqual(args.operation, name)

    def test_rendered_grouped_examples_resolve_to_equivalent_operations(self):
        consolidated = {"dashboard": "resource-summary", "task-status": "task-summary"}
        for name, spec in {**dibu.SUMMARY_OPS, **dibu.CAT}.items():
            for example in spec["cli"]["examples"]:
                command = dibu.canonical_command(name) + example[len(name) :]
                with self.subTest(command=command):
                    args, _ = dibu.parse_cli(shlex.split(command))
                    self.assertEqual(args.operation, consolidated.get(name, name))

    def test_named_ids_keep_write_preview_and_path_escaping(self):
        out = io.StringIO()
        with (
            patch("sys.argv", ["dibu", "image-delete", "--id", "42"]),
            patch.object(
                dibu,
                "auth_config",
                side_effect=AssertionError("Preview must not authenticate"),
            ),
            contextlib.redirect_stdout(out),
        ):
            dibu.main()
        result = json.loads(out.getvalue())
        self.assertEqual(result["query"]["image_id"], 42)
        self.assertTrue(result["preview"])
        _, params = dibu.parse_cli(["extension-status", "--id", "42", "--operation-id", "a/b"])
        self.assertEqual(
            dibu.prepare("extension-status", params, None)[1],
            "/container/42/extensions/a%2Fb/",
        )

    def test_named_creation_units_and_body_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            body = pathlib.Path(directory) / "body.json"
            body.write_text(json.dumps({"password": "fixture-secret", "is_VM": False}))
            argv = [
                "dibu",
                "container-create",
                "--body-file",
                str(body),
                "--image",
                "42",
                "--cpu",
                "2",
                "--memory",
                "4Gi",
                "--duration",
                "10m",
                "--command",
                "echo fixture",
                "--mode",
                "task",
            ]
            out = io.StringIO()
            with (
                patch("sys.argv", argv),
                patch.object(dibu, "request") as request,
                contextlib.redirect_stdout(out),
            ):
                dibu.main()
            request.assert_not_called()
            result = json.loads(out.getvalue())
            self.assertEqual(result["body"]["duration"], 600)
            self.assertEqual(result["body"]["password"], "[REDACTED]")
            body.write_text(json.dumps({"password": "fixture-secret", "is_VM": True}))
            with (
                patch("sys.argv", argv),
                self.assertRaisesRegex(ValueError, "Conflicting alias"),
            ):
                dibu.main()

    def test_sampled_write_receipts_preserve_connection_and_http_status(self):
        for operation, response in (
            (
                "container-create",
                {"message": "success", "port": 12345, "IP": "fixture-address"},
            ),
            ("experiment-stop", {"message": "fixture accepted"}),
            ("container-delete", {"status": 204, "text": ""}),
            ("container-history-delete", {"status": 204, "text": ""}),
            ("image-delete", {"status": 204, "text": ""}),
            ("image-permanent", {"status": 200, "text": ""}),
        ):
            with self.subTest(operation=operation):
                result = dibu.compact_response(operation, response)
                self.assertEqual(result, response)
                self.assertNotIn("success", result)
                self.assertNotIn("state", result)

    def test_image_save_status_omits_runtime_internals_but_preserves_diagnostics(self):
        response = {
            "state": "finished",
            "result": {"digest": "fixture", "size_bytes": 123},
            "requested_at": "before",
            "updated_at": "after",
            "warnings": ["preserve"],
            "client_data": {
                "operation_id": "fixture-op",
                "image_name": "fixture:v1",
                "node_name": "fixture-node",
                "is_temporary": False,
                "pod_uid": "fixture-uid",
                "container_name_or_id": "fixture-id",
            },
        }
        compact = dibu.compact_response("image-save-status", response)
        self.assertEqual(compact["state"], "finished")
        self.assertEqual(compact["result"], response["result"])
        self.assertEqual(compact["warnings"], ["preserve"])
        self.assertEqual(compact["client_data"]["operation_id"], "fixture-op")
        self.assertNotIn("pod_uid", compact["client_data"])
        self.assertIn("pod_uid", response["client_data"])
        response["client_data"]["new_diagnostic"] = "preserve"
        self.assertEqual(dibu.compact_response("image-save-status", response), response)
        self.assertEqual(dibu.compact_response("image-save-status", {}), {})

    def test_compact_preserves_pagination_diagnostics_and_actual_status(self):
        response = {
            "count": 200,
            "next": "/page/2",
            "previous": None,
            "warnings": ["stale"],
            "results": [
                {
                    "container_id": 42,
                    "status": "Pending",
                    "cmd": "large command",
                    "password": "private",
                    "num_gpu": 2,
                }
            ],
        }
        original = copy.deepcopy(response)
        result = dibu.compact_response("tasks", response)
        self.assertEqual(result["results"], [{"container_id": 42, "status": "Pending", "num_gpu": 2}])
        self.assertEqual(result["next"], "/page/2")
        self.assertEqual(result["warnings"], ["stale"])
        self.assertEqual(response, original)

    def test_compact_falls_back_for_new_fields_and_unknown_shapes(self):
        for response in (
            {"results": [{"container_id": 1, "new_diagnostic": "check me", "cmd": "keep"}]},
            {"results": ["unexpected"]},
            {"new_list": []},
            {"results": [{"other_id": 1}]},
        ):
            self.assertEqual(dibu.compact_response("tasks", response), response)
        write = {
            "data": {"operation_id": 1, "estimate_fingerprint": "required"},
            "warnings": ["check"],
        }
        self.assertEqual(dibu.compact_response("container-create", write), write)

    def test_compact_handles_data_wrapper_arrays_and_empty_pages(self):
        response = {
            "data": [{"image_id": 1, "image_name": "ubuntu", "metadata": {"large": True}}],
            "request_id": "abc",
            "warnings": [],
        }
        self.assertEqual(
            dibu.compact_response("images", response),
            {
                "data": [{"image_id": 1, "image_name": "ubuntu"}],
                "request_id": "abc",
                "warnings": [],
            },
        )
        self.assertEqual(
            dibu.compact_response("tasks", {"results": [], "next": None}),
            {"results": [], "next": None},
        )

    def test_observed_workload_schema_keeps_resource_and_lifecycle_details(self):
        row = {key: None for key in dibu.LIST_EXTRA_FIELDS["tasks"]}
        row.update(
            container_id=42,
            status="Pending",
            password="fixture-only",
            cmd="fixture command",
            node_ip="fixture address",
            port=123,
            pod_name="fixture pod",
            timing={"remaining_seconds": None},
            dra_request={"definition": {"mode": "mig", "memory_mib": 4096}},
            can_extend=False,
            image_save={"state": "failed", "error": "fixture"},
        )
        for operation in ("tasks", "experiments"):
            result = dibu.compact_response(operation, {"results": [row], "next": "page2"})
            after = result["results"][0]
            for key in ("password", "cmd", "node_ip", "port", "pod_name"):
                self.assertNotIn(key, after)
            for key in ("can_extend", "image_save"):
                self.assertEqual(after[key], row[key])
            self.assertNotIn("dra_request", after)
            self.assertEqual(after["timing"], {"state": None})
            for key in (
                "duration",
                "requested_duration_minutes",
                "cur_duration",
                "add_hours",
                "is_VM",
                "manual_restart_used",
            ):
                self.assertNotIn(key, after)
            self.assertEqual(result["next"], "page2")

    def test_observed_image_file_and_profile_fields(self):
        image = {
            "image_id": 1,
            "name": "fixture",
            "tag": "v1",
            "nickname": "display",
            "record_datetime": "fixture date",
            "is_push": False,
            "node": 1,
        }
        result = dibu.compact_response("images", {"results": [image]})["results"][0]
        self.assertNotIn("nickname", result)
        self.assertEqual(result["tag"], "v1")
        self.assertFalse(result["is_push"])
        files = [
            {
                "name": "fixture",
                "modified_date": "fixture date",
                "type": "dir",
                "size": None,
            }
        ]
        self.assertEqual(dibu.compact_response("files", files), files)
        profile = {
            "user_id": 1,
            "username": "fixture",
            "gputime": 0,
            "wechat_avatar_url": "fixture",
        }
        self.assertEqual(
            dibu.compact_response("profile", profile),
            {"user_id": 1, "username": "fixture", "gputime": 0},
        )
        profile["new_diagnostic"] = "preserve"
        self.assertEqual(dibu.compact_response("profile", profile), profile)

    def test_cli_raw_aliases_bypass_projection(self):
        response = {
            "results": [
                {
                    "container_id": 1,
                    "cmd": "full command",
                    "dra_request": {"parameters": {"count": 2}},
                    "timing": {"state": "running", "elapsed_seconds": 10},
                }
            ]
        }
        for flags in ([], ["--raw"], ["-v"], ["--verbose"]):
            out = io.StringIO()
            with (
                patch("sys.argv", ["dibu", "tasks", *flags]),
                patch.object(dibu, "auth_config", return_value=("fixture", "fixture")),
                patch.object(dibu, "request", return_value=response),
                contextlib.redirect_stdout(out),
            ):
                dibu.main()
            expected = response if flags else {"results": [{"container_id": 1, "timing": {"state": "running"}}]}
            self.assertEqual(json.loads(out.getvalue()), expected)

    def test_raw_summary_keeps_page_responses(self):
        response = {
            "results": [{"container_id": 1, "cmd": "full command"}],
            "next": None,
        }
        with (
            patch.object(dibu, "auth_config", return_value=("fixture", "fixture")),
            patch.object(dibu, "request", return_value=response),
        ):
            result = dibu.run_summary("task-summary", {}, raw=True)
        self.assertEqual(len(result["responses"]), 3)
        self.assertEqual(result["responses"][0]["response"], response)
        self.assertEqual(result["responses"][0]["query"]["operate_id"], 1)

    def test_raw_does_not_bypass_preview_or_secret_output_requirement(self):
        out = io.StringIO()
        with (
            patch(
                "sys.argv",
                ["dibu", "password-change", "--param", "password=private", "--raw"],
            ),
            patch.object(dibu, "request") as request,
            contextlib.redirect_stdout(out),
        ):
            dibu.main()
        request.assert_not_called()
        self.assertTrue(json.loads(out.getvalue())["preview"])
        self.assertNotIn("private", out.getvalue())
        with (
            patch("sys.argv", ["dibu", "access-token-create", "--execute", "--raw"]),
            patch.object(dibu, "request") as request,
            self.assertRaisesRegex(ValueError, "--output"),
        ):
            dibu.main()
        request.assert_not_called()

    def test_output_saves_full_response_privately(self):
        response = b'{"results":[{"container_id":1,"cmd":"full command"}]}'
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "response.json"
            target.touch(mode=0o644)
            with patch("urllib.request.build_opener") as opener:
                reply = opener.return_value.open.return_value.__enter__.return_value
                reply.read.return_value = response
                reply.status = 200
                result = dibu.request(
                    "http://fixture",
                    "Token fixture",
                    {"method": "GET"},
                    "/",
                    {},
                    None,
                    {},
                    str(target),
                )
            self.assertEqual(target.read_bytes(), response)
            self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)
            self.assertNotIn("results", result)

    def test_create_rejects_blank_password_and_mismatched_gpu_count(self):
        body = {
            "password": "",
            "is_VM": False,
            "cmd": "echo ok",
            "num_gpu": 2,
            "gpu_selection": {"count": 2},
        }
        with self.assertRaisesRegex(ValueError, "password"):
            dibu.prepare("container-create", {}, body)
        body["password"] = "fixture-not-a-real-password"
        body["gpu_selection"]["count"] = 1
        with self.assertRaisesRegex(ValueError, "num_gpu"):
            dibu.prepare("container-create", {}, body)
        body["gpu_selection"]["count"] = 2
        self.assertEqual(dibu.prepare("container-create", {}, body)[3]["num_gpu"], 2)

    def test_task_requires_command_but_experiment_does_not(self):
        body = {"password": "fixture", "is_VM": False, "cmd": ""}
        with self.assertRaisesRegex(ValueError, "cmd"):
            dibu.prepare("container-create", {}, body)
        body["is_VM"] = True
        dibu.prepare("container-create", {}, body)

    def test_preview_redacts_nested_secrets_without_modifying_request(self):
        body = {
            "password": "private",
            "nested": {"accessToken": "private-token"},
            "cmd": "echo ok",
        }
        result = dibu.redact(body)
        self.assertEqual(result["password"], "[REDACTED]")
        self.assertEqual(result["nested"]["accessToken"], "[REDACTED]")
        self.assertEqual(body["password"], "private")
        self.assertEqual(result["cmd"], "echo ok")

    def test_availability_excludes_disabled_nodes_and_keeps_unknown(self):
        dashboard = {
            "stale": False,
            "errors": {},
            "sampled_at_ms": 100,
            "nodes": [
                {"node_id": 1, "node_status": "Ready", "gpu_remain_num": 3},
                {
                    "node_id": 2,
                    "node_status": "SchedulingDisabled",
                    "gpu_remain_num": 8,
                },
                {"node_id": 3, "node_status": "Ready", "gpu_remain_num": None},
            ],
        }
        result = dibu.resource_summary(dashboard)
        self.assertEqual([n["node_id"] for n in result["nodes"]], [1, 3])
        self.assertEqual([n["schedulable_free_gpus"] for n in result["nodes"]], [3, None])
        all_nodes = dibu.resource_summary(dashboard, include_all=True)
        self.assertEqual([n["schedulable_free_gpus"] for n in all_nodes["nodes"]], [3, None, None])
        stale = copy.deepcopy(dashboard)
        stale["stale"] = True
        self.assertTrue(all(n["schedulable_free_gpus"] is None for n in dibu.resource_summary(stale)["nodes"]))

    def test_resource_summary_only_requests_dashboard(self):
        with (
            patch.object(dibu, "auth_config", return_value=("http://fixture", "fixture")),
            patch.object(dibu, "request", return_value={"nodes": [], "stale": False}) as request,
        ):
            dibu.run_summary("resource-summary", {})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[3], "/node/dashboard/")

    def test_task_status_searches_pages_and_reports_actual_status_and_events(self):
        calls = []

        def fake_request(base, auth, op, path, q, b, headers):
            calls.append((path, dict(q)))
            if path == "/container/getPodEvent/":
                return {"events": {"pod": [{"reason": "FailedScheduling"}]}}
            if q["operate_id"] == 1 and q["page"] == 1:
                return {"results": [{"container_id": 1}], "next": "next-page"}
            if q["operate_id"] in (1, 2):
                return {
                    "results": [
                        {
                            "container_id": 42,
                            "status": "Pending",
                            "password": "must-not-return",
                        }
                    ],
                    "next": None,
                }
            return {"results": [], "next": None}

        with (
            patch.object(dibu, "auth_config", return_value=("http://fixture", "fixture")),
            patch.object(dibu, "request", side_effect=fake_request),
        ):
            result = dibu.run_summary("task-status", {"container_id": 42})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["tasks"][0]["status"], "Pending")
        self.assertNotIn("password", result["tasks"][0])
        self.assertEqual(result["events"]["pod"][0]["reason"], "FailedScheduling")
        self.assertTrue(any(q.get("page") == 2 for _, q in calls))


if __name__ == "__main__":
    unittest.main()
