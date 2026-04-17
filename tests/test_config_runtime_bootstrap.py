import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import leam.config as config_module


class ConfigRuntimeBootstrapTests(unittest.TestCase):
    def _make_cst_install(self, base_dir: Path, year: int) -> Path:
        root = base_dir / f"CST Studio Suite {year}"
        (root / "AMD64" / "python_cst_libraries").mkdir(parents=True, exist_ok=True)
        return root

    def _make_hfss_install(self, base_dir: Path, version: str) -> Path:
        root = base_dir / version / "AnsysEM"
        (root / "syslib").mkdir(parents=True, exist_ok=True)
        (root / "Win64").mkdir(parents=True, exist_ok=True)
        return root

    def test_detect_latest_cst_install_prefers_highest_year(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            base_x86 = Path(tempdir) / "Program Files (x86)"
            base_x64 = Path(tempdir) / "Program Files"
            self._make_cst_install(base_x86, 2024)
            newest = self._make_cst_install(base_x64, 2025)

            with patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (base_x86, base_x64),
            ), patch.dict(os.environ, {}, clear=True):
                detected = config_module._detect_latest_cst_install({})

        self.assertIsNotNone(detected)
        self.assertEqual(detected["path"], str(newest.resolve()))
        self.assertEqual(
            detected["python_libraries_path"],
            str((newest / "AMD64" / "python_cst_libraries").resolve()),
        )

    def test_detect_latest_hfss_install_prefers_highest_ansysem_env(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            install_root = Path(tempdir) / "ANSYS Inc"
            older = self._make_hfss_install(install_root, "v242")
            newest = self._make_hfss_install(install_root, "v251")

            with patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                install_root,
            ), patch.dict(
                os.environ,
                {
                    "ANSYSEM_ROOT242": str(older),
                    "ANSYSEM_ROOT251": str(newest),
                },
                clear=True,
            ):
                detected = config_module._detect_latest_hfss_install({})

        self.assertIsNotNone(detected)
        self.assertEqual(detected["path"], str(newest.resolve()))

    def test_normalize_hfss_root_accepts_legacy_win64_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            hfss_root = self._make_hfss_install(Path(tempdir), "v251")

            normalized = config_module._normalize_hfss_root(str(hfss_root / "Win64"))

        self.assertEqual(normalized, str(hfss_root.resolve()))

    def test_load_config_prefers_leam_config_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "custom-config.json"
            config_path.write_text(
                '{\n  "custom_setting": "override-value"\n}\n',
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {config_module.ENV_LEAM_CONFIG: str(config_path)},
                clear=True,
            ):
                loaded = config_module.load_config()

        self.assertEqual(loaded["custom_setting"], "override-value")

    def test_load_config_ignores_cwd_legacy_config_json(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            cwd_dir = Path(tempdir) / "cwd"
            user_config_path = home_dir / ".leam" / "config.json"
            cwd_config_path = cwd_dir / "config.json"
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            cwd_dir.mkdir(parents=True, exist_ok=True)
            user_config_path.write_text(
                '{\n  "custom_setting": "user-value"\n}\n',
                encoding="utf-8",
            )
            cwd_config_path.write_text(
                '{\n  "custom_setting": "cwd-value"\n}\n',
                encoding="utf-8",
            )

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module.Path,
                "cwd",
                return_value=cwd_dir,
            ), patch.dict(os.environ, {}, clear=True):
                loaded = config_module.load_config()

        self.assertEqual(loaded["custom_setting"], "user-value")

    def test_resolve_openai_api_key_reads_environment_only(self) -> None:
        with patch.dict(
            os.environ,
            {config_module.ENV_OPENAI_API_KEY: "env-key"},
            clear=True,
        ):
            resolved = config_module.resolve_openai_api_key(
                {"openai_api_key": "config-key"}
            )

        self.assertEqual(resolved, "env-key")

    def test_ensure_openai_api_key_ignores_config_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text(
                '{\n  "openai_api_key": "config-key"\n}\n',
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    config_module.ensure_openai_api_key(str(config_path))

    def test_resolve_cst_path_prefers_explicit_config_over_newer_detected_install(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            base_dir = Path(tempdir) / "Program Files"
            pinned = self._make_cst_install(base_dir, 2024)
            self._make_cst_install(base_dir, 2025)

            with patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (base_dir,),
            ), patch.dict(os.environ, {}, clear=True):
                resolved = config_module.resolve_cst_path(
                    {"cst_path": str(pinned)}
                )

        self.assertEqual(resolved, str(pinned.resolve()))

    def test_resolve_hfss_path_prefers_explicit_config_over_newer_detected_install(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            install_root = Path(tempdir) / "ANSYS Inc"
            pinned = self._make_hfss_install(install_root, "v242")
            self._make_hfss_install(install_root, "v251")

            with patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                install_root,
            ), patch.dict(os.environ, {}, clear=True):
                resolved = config_module.resolve_hfss_path(
                    {"hfss_path": str(pinned)}
                )

        self.assertEqual(resolved, str(pinned.resolve()))

    def test_validate_hfss_path_treats_manual_override_as_advanced_fallback(self) -> None:
        is_valid, message = config_module.validate_hfss_path(None)

        self.assertFalse(is_valid)
        self.assertIn("not detected automatically", message)
        self.assertIn("advanced override", message)

    def test_validate_cst_path_treats_manual_override_as_advanced_fallback(self) -> None:
        is_valid, message = config_module.validate_cst_path(None)

        self.assertFalse(is_valid)
        self.assertIn("not detected automatically", message)
        self.assertIn("advanced override", message)

    def test_bootstrap_does_not_write_or_overwrite_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            user_config_path = home_dir / ".leam" / "config.json"
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            user_config_path.write_text(
                '{\n  "username": "alice",\n  "cst_path": "C:\\\\PinnedCST",\n  "custom": {"keep": true}\n}\n',
                encoding="utf-8",
            )

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module,
                "_config_search_paths",
                return_value=[user_config_path],
            ), patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (Path(tempdir) / "Program Files",),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                Path(tempdir) / "ANSYS Inc",
            ), patch.dict(
                os.environ,
                {},
                clear=True,
            ), patch(
                "leam.config._write_user_config"
            ) as write_user_config:
                updated = config_module._bootstrap_desktop_runtime_config()

            written = config_module._read_config_file(user_config_path)

        self.assertEqual(updated["username"], "alice")
        self.assertEqual(updated["cst_path"], "C:\\PinnedCST")
        self.assertEqual(written["custom"], {"keep": True})
        write_user_config.assert_not_called()

    def test_bootstrap_injects_cst_runtime_path_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            user_config_path = home_dir / ".leam" / "config.json"
            cst_install = self._make_cst_install(Path(tempdir) / "Program Files", 2025)
            libraries_path = str((cst_install / "AMD64" / "python_cst_libraries").resolve())
            user_config_path.parent.mkdir(parents=True, exist_ok=True)
            user_config_path.write_text(
                json.dumps(
                    {
                        "cst_path": str(cst_install.resolve()),
                    }
                ),
                encoding="utf-8",
            )
            original_sys_path = list(sys.path)

            def fake_find_spec(name: str):
                if name != "cst.interface":
                    return None
                return object() if libraries_path in sys.path else None

            try:
                with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                    config_module,
                    "_config_search_paths",
                    return_value=[user_config_path],
                ), patch.dict(os.environ, {}, clear=True), patch(
                    "leam.config.importlib.util.find_spec",
                    side_effect=fake_find_spec,
                ):
                    updated = config_module._bootstrap_desktop_runtime_config()
            finally:
                injected_path_present = libraries_path in sys.path
                sys.path[:] = original_sys_path

        self.assertTrue(injected_path_present)
        self.assertEqual(updated["cst_path"], str(cst_install.resolve()))
        self.assertNotIn("cst_python_libraries_path", updated)

    def test_bootstrap_writes_detected_cst_path_on_first_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            cst_base = Path(tempdir) / "Program Files"
            newest_cst = self._make_cst_install(cst_base, 2025)

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (cst_base,),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                Path(tempdir) / "ANSYS Inc",
            ), patch.dict(os.environ, {}, clear=True), patch(
                "leam.config._ensure_cst_runtime_connected",
                return_value=(False, ""),
            ):
                updated = config_module._bootstrap_desktop_runtime_config()

            written = config_module._read_config_file(home_dir / ".leam" / "config.json")

        self.assertEqual(updated["cst_path"], str(newest_cst.resolve()))
        self.assertNotIn("hfss_path", updated)
        self.assertEqual(written["cst_path"], str(newest_cst.resolve()))
        self.assertFalse(written["allow_unsafe_execution"])

    def test_bootstrap_writes_detected_hfss_path_on_first_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            hfss_base = Path(tempdir) / "ANSYS Inc"
            newest_hfss = self._make_hfss_install(hfss_base, "v251")

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (Path(tempdir) / "Program Files",),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                hfss_base,
            ), patch.dict(os.environ, {}, clear=True), patch(
                "leam.config._ensure_cst_runtime_connected",
                return_value=(False, ""),
            ):
                updated = config_module._bootstrap_desktop_runtime_config()

            written = config_module._read_config_file(home_dir / ".leam" / "config.json")

        self.assertEqual(updated["hfss_path"], str(newest_hfss.resolve()))
        self.assertNotIn("cst_path", updated)
        self.assertEqual(written["hfss_path"], str(newest_hfss.resolve()))
        self.assertFalse(written["allow_unsafe_execution"])

    def test_bootstrap_writes_both_detected_paths_on_first_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            cst_base = Path(tempdir) / "Program Files"
            hfss_base = Path(tempdir) / "ANSYS Inc"
            newest_cst = self._make_cst_install(cst_base, 2025)
            newest_hfss = self._make_hfss_install(hfss_base, "v251")

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (cst_base,),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                hfss_base,
            ), patch.dict(os.environ, {}, clear=True), patch(
                "leam.config._ensure_cst_runtime_connected",
                return_value=(False, ""),
            ):
                updated = config_module._bootstrap_desktop_runtime_config()

            written = config_module._read_config_file(home_dir / ".leam" / "config.json")

        self.assertEqual(updated["cst_path"], str(newest_cst.resolve()))
        self.assertEqual(updated["hfss_path"], str(newest_hfss.resolve()))
        self.assertEqual(written["cst_path"], str(newest_cst.resolve()))
        self.assertEqual(written["hfss_path"], str(newest_hfss.resolve()))
        self.assertFalse(written["allow_unsafe_execution"])

    def test_bootstrap_does_not_write_empty_config_when_no_backend_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"

            with patch.object(config_module.Path, "home", return_value=home_dir), patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (Path(tempdir) / "Program Files",),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                Path(tempdir) / "ANSYS Inc",
            ), patch.dict(os.environ, {}, clear=True), patch(
                "leam.config._ensure_cst_runtime_connected",
                return_value=(False, ""),
            ), patch("leam.config._write_user_config") as write_user_config:
                updated = config_module._bootstrap_desktop_runtime_config()

        self.assertEqual(updated, {})
        write_user_config.assert_not_called()

    def test_ensure_cst_runtime_connected_handles_missing_parent_module(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cst_install = self._make_cst_install(Path(tempdir) / "Program Files", 2025)
            libraries_path = str((cst_install / "AMD64" / "python_cst_libraries").resolve())
            original_sys_path = list(sys.path)

            def fake_find_spec(name: str):
                if name != "cst.interface":
                    return None
                if libraries_path in sys.path:
                    return object()
                raise ModuleNotFoundError("No module named 'cst'")

            try:
                with patch(
                    "leam.config.importlib.util.find_spec",
                    side_effect=fake_find_spec,
                ):
                    connected, message = config_module._ensure_cst_runtime_connected(
                        str(cst_install.resolve()),
                        libraries_path,
                    )
            finally:
                sys.path[:] = original_sys_path

        self.assertTrue(connected)
        self.assertEqual(message, "")

    def test_module_spec_exists_handles_missing_parent_module(self) -> None:
        with patch(
            "leam.utils.module_utils.importlib.util.find_spec",
            side_effect=ModuleNotFoundError("No module named 'ansys'"),
        ):
            available = config_module._module_spec_exists("ansys.aedt.core")

        self.assertFalse(available)

    def test_dry_run_handles_missing_optional_hfss_parent_module(self) -> None:
        output = StringIO()

        def fake_find_spec(name: str):
            if name == "cst.interface":
                return None
            if name == "ansys.aedt.core":
                raise ModuleNotFoundError("No module named 'ansys'")
            return None

        with patch.object(config_module, "load_config", return_value={}), patch.object(
            config_module,
            "autofill_simulator_paths",
            return_value={},
        ), patch(
            "leam.utils.module_utils.importlib.util.find_spec",
            side_effect=fake_find_spec,
        ), redirect_stdout(output):
            exit_code = config_module.main(["--dry-run"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Resolved LEAM config (dry run):", output.getvalue())
        self.assertIn(
            f'missing; reinstall LEAM with `{config_module.RECOMMENDED_DESKTOP_INSTALL_COMMAND}`',
            output.getvalue(),
        )

    def test_print_example_outputs_packaged_template_without_writing(self) -> None:
        output = StringIO()

        with patch("leam.config._write_user_config") as write_user_config, redirect_stdout(
            output
        ):
            exit_code = config_module.main(["--print-example"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(payload["allow_unsafe_execution"])
        self.assertEqual(payload["openai_timeout_seconds"], 600)
        write_user_config.assert_not_called()

    def test_write_user_config_uses_leam_config_env_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "custom-config.json"

            with patch.dict(
                os.environ,
                {config_module.ENV_LEAM_CONFIG: str(config_path)},
                clear=True,
            ):
                written_path = config_module._write_user_config({})
                self.assertEqual(written_path, config_path)
                self.assertTrue(config_path.exists())
                self.assertEqual(config_module._read_config_file(config_path), {})

    def test_autofill_simulator_paths_detects_missing_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cst_base = Path(tempdir) / "Program Files"
            hfss_base = Path(tempdir) / "ANSYS Inc"
            newest_cst = self._make_cst_install(cst_base, 2025)
            newest_hfss = self._make_hfss_install(hfss_base, "v251")

            with patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (cst_base,),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                hfss_base,
            ), patch.dict(os.environ, {}, clear=True):
                updated = config_module.autofill_simulator_paths({})

        self.assertEqual(updated["cst_path"], str(newest_cst.resolve()))
        self.assertEqual(updated["hfss_path"], str(newest_hfss.resolve()))

    def test_autofill_simulator_paths_preserves_pinned_values(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cst_base = Path(tempdir) / "Program Files"
            hfss_base = Path(tempdir) / "ANSYS Inc"
            pinned_cst = self._make_cst_install(cst_base, 2024)
            pinned_hfss = self._make_hfss_install(hfss_base, "v242")
            self._make_cst_install(cst_base, 2025)
            self._make_hfss_install(hfss_base, "v251")

            with patch.object(
                config_module,
                "_CST_INSTALL_ROOTS",
                (cst_base,),
            ), patch.object(
                config_module,
                "_HFSS_INSTALL_ROOT",
                hfss_base,
            ), patch.dict(os.environ, {}, clear=True):
                updated = config_module.autofill_simulator_paths(
                    {
                        "cst_path": str(pinned_cst),
                        "hfss_path": str(pinned_hfss),
                    }
                )

        self.assertEqual(updated["cst_path"], str(pinned_cst.resolve()))
        self.assertEqual(updated["hfss_path"], str(pinned_hfss.resolve()))

    def test_resolve_allow_unsafe_execution_prefers_env_override(self) -> None:
        with patch.dict(
            os.environ,
            {config_module.ENV_ALLOW_UNSAFE_EXECUTION: "1"},
            clear=True,
        ):
            resolved = config_module.resolve_allow_unsafe_execution(
                {"allow_unsafe_execution": False}
            )

        self.assertTrue(resolved)

    def test_resolve_allow_unsafe_execution_defaults_to_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            resolved = config_module.resolve_allow_unsafe_execution({})

        self.assertFalse(resolved)


if __name__ == "__main__":
    unittest.main()
