import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from leam.backends.hfss.tools import hfss_runner as hfss_runner_module
from leam.backends.hfss.tools.hfss_runner import HfssRunner


class _FakePolylineSegment:
    def __init__(self, segment_type=None, **kwargs):
        self.type = segment_type or kwargs.get("segment_type")
        self.num_seg = kwargs.get("num_seg", 0)
        self.num_points = kwargs.get("num_points", 0)
        if self.type == "Line":
            self.num_points = 2
        elif self.type in {"Arc", "AngularArc"}:
            self.num_points = 3
        self.kwargs = {"segment_type": self.type, **kwargs}


class _FakeModeler:
    def __init__(self, owner):
        self.owner = owner

    def record(self, label: str) -> None:
        self.owner.events.append(("modeler", label))

    def create_box(self, origin, sizes, name=None, material=None, **kwargs):
        self.owner.events.append(
            ("create_box", origin, sizes, name, material)
        )
        if self.owner.create_box_result is False:
            return False
        return types.SimpleNamespace(name=name or "Box1")

    def create_polyline(self, points, name=None, **kwargs):
        self.owner.events.append(("create_polyline", points, name))
        if self.owner.create_polyline_result is False:
            return False
        return _FakePolyline(
            self.owner,
            name=name or "Polyline1",
            insert_segment_result=self.owner.insert_segment_result,
        )


class _FakePolyline:
    def __init__(self, owner, name: str, insert_segment_result: bool = True):
        self.owner = owner
        self.name = name
        self.insert_segment_result = insert_segment_result

    def insert_segment(self, points, segment=None):
        self.owner.events.append(
            ("insert_segment", self.name, points, segment)
        )
        return self.insert_segment_result


class _FakeHfss:
    instances = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.events = []
        self.variables = {}
        self.saved_calls = []
        self.release_calls = []
        self.create_box_result = True
        self.create_polyline_result = True
        self.insert_segment_result = True
        self.modeler = _FakeModeler(self)
        type(self).instances.append(self)

    def __setitem__(self, key, value):
        self.variables[key] = value
        self.events.append(("set", key, value))

    def record(self, label: str) -> None:
        self.events.append(("app", label))

    def save_project(self, file_name=None, overwrite=True, refresh_ids=False):
        self.saved_calls.append(
            {
                "file_name": file_name,
                "overwrite": overwrite,
                "refresh_ids": refresh_ids,
            }
        )
        return True

    def release_desktop(self, close_projects=True, close_desktop=True):
        self.release_calls.append(
            {
                "close_projects": close_projects,
                "close_desktop": close_desktop,
            }
        )


class HfssRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeHfss.instances = []
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_script(self, name: str, content: str) -> str:
        path = Path(self.tempdir.name) / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _patch_aedt_core(self):
        fake_core = types.SimpleNamespace(Hfss=_FakeHfss, Desktop=object)
        fake_primitives = types.SimpleNamespace(
            PolylineSegment=_FakePolylineSegment
        )

        def _fake_import(name: str):
            if name == "ansys.aedt.core":
                return fake_core
            if name == "ansys.aedt.core.modeler.cad.primitives":
                return fake_primitives
            raise ImportError(name)

        return patch(
            "leam.backends.hfss.tools.hfss_runner.importlib.import_module",
            side_effect=_fake_import,
        )

    def test_create_project_executes_build_tasks_and_saves(self) -> None:
        parameters = self._write_script(
            "parameters.py",
            'hfss["$w1"] = "1mm"\n'
            'hfss.record("parameters")\n',
        )
        model_3d = self._write_script(
            "model_3d.py",
            'hfss.modeler.record("model_3d")\n',
        )
        boolean = self._write_script(
            "boolean.py",
            'aedtapp.record("boolean")\n',
        )
        save_path = str(Path(self.tempdir.name) / "projects" / "antenna.aedt")

        with self._patch_aedt_core():
            runner = HfssRunner(
                design_name="Patch1",
                new_desktop=True,
                allow_unsafe_execution=True,
            )
            runner.set_build_tasks(
                {
                    "Parameters": parameters,
                    "3D Model": model_3d,
                    "Boolean": boolean,
                }
            )
            created = runner.create_project(
                save_path=save_path,
                close_project_after_save=False,
            )

            self.assertEqual(created, str(Path(save_path).resolve()))
            app = _FakeHfss.instances[0]
            self.assertEqual(app.init_kwargs["project"], None)
            self.assertEqual(app.init_kwargs["design"], "Patch1")
            self.assertEqual(
                app.events,
                [
                    ("set", "$w1", "1mm"),
                    ("app", "parameters"),
                    ("modeler", "model_3d"),
                    ("app", "boolean"),
                ],
            )
            self.assertEqual(
                app.saved_calls,
                [
                    {
                        "file_name": str(Path(save_path).resolve()),
                        "overwrite": True,
                        "refresh_ids": False,
                    }
                ],
            )

            runner.close_project()
            self.assertEqual(
                app.release_calls,
                [{"close_projects": True, "close_desktop": True}],
            )

    def test_apply_parameter_updates_opens_existing_project_and_saves(self) -> None:
        existing_project = Path(self.tempdir.name) / "existing.aedt"
        existing_project.write_text("stub", encoding="utf-8")
        update_script = self._write_script(
            "parameter_update.py",
            'hfss["$w1"] = "2mm"\n'
            'hfss.record("update")\n',
        )
        updated_project = str(Path(self.tempdir.name) / "updated.aedt")

        with self._patch_aedt_core():
            runner = HfssRunner(
                project_path=str(existing_project),
                design_name="Patch1",
                new_desktop=False,
                allow_unsafe_execution=True,
            )
            runner.set_parameter_tasks({"Update Parameters": update_script})
            saved = runner.apply_parameter_updates(save_path=updated_project)

            self.assertEqual(saved, str(Path(updated_project).resolve()))
            app = _FakeHfss.instances[0]
            self.assertEqual(
                app.init_kwargs["project"],
                str(existing_project.resolve()),
            )
            self.assertEqual(app.variables["$w1"], "2mm")
            self.assertEqual(
                app.saved_calls[-1],
                {
                    "file_name": str(Path(updated_project).resolve()),
                    "overwrite": True,
                    "refresh_ids": False,
                },
            )
            self.assertEqual(
                app.release_calls,
                [{"close_projects": True, "close_desktop": False}],
            )

    def test_nonexistent_project_path_is_passed_to_pyaedt_for_direct_creation(self) -> None:
        new_project = Path(self.tempdir.name) / "nested" / "antenna.aedt"

        with self._patch_aedt_core():
            runner = HfssRunner(
                project_path=str(new_project),
                design_name="Patch1",
                new_desktop=True,
                allow_unsafe_execution=True,
            )

            app = _FakeHfss.instances[0]
            self.assertEqual(
                app.init_kwargs["project"],
                str(new_project.resolve()),
            )
            self.assertTrue(new_project.parent.exists())
            runner.close_project()

    def test_missing_script_path_raises_file_not_found(self) -> None:
        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            runner.set_build_tasks({"Missing": str(Path(self.tempdir.name) / "x.py")})

            with self.assertRaises(FileNotFoundError):
                runner.run_build_tasks()

    def test_missing_pyaedt_raises_clear_runtime_error(self) -> None:
        with patch(
            "leam.backends.hfss.tools.hfss_runner.importlib.import_module",
            side_effect=ImportError("missing"),
        ):
            with self.assertRaises(RuntimeError):
                HfssRunner(allow_unsafe_execution=True)

    def test_constructor_respects_explicit_unsafe_execution_disable(self) -> None:
        with patch(
            "leam.backends.hfss.tools.hfss_runner.load_config",
            return_value={"allow_unsafe_execution": False},
        ), patch(
            "leam.backends.hfss.tools.hfss_runner.importlib.import_module"
        ) as import_module:
            with self.assertRaises(RuntimeError) as ctx:
                HfssRunner()

        self.assertIn("LEAM_ALLOW_UNSAFE_EXECUTION=1", str(ctx.exception))
        import_module.assert_not_called()

    def test_false_return_from_guarded_modeler_call_raises_runtime_error(self) -> None:
        model_3d = self._write_script(
            "model_3d.py",
            'hfss.modeler.create_box(origin=[0, 0, 0], sizes=[1, 1, 1], name="Box1", material="vacuum")\n',
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            app = _FakeHfss.instances[0]
            app.create_box_result = False
            runner.set_build_tasks({"3D Model": model_3d})

            with self.assertRaises(RuntimeError) as ctx:
                runner.run_build_tasks()

        self.assertIn("HFSS task `3D Model` failed", str(ctx.exception))
        self.assertIn("hfss.modeler.create_box", str(ctx.exception))
        self.assertIn("returned False", str(ctx.exception))

    def test_false_return_from_guarded_object_method_raises_runtime_error(self) -> None:
        model_2d = self._write_script(
            "model_2d.py",
            'profile = hfss.modeler.create_polyline(points=[[0, 0, 0], [1, 0, 0]], name="SlotProfile")\n'
            'profile.insert_segment(points=[[1, 0, 0], [1, 1, 0]], segment="Line")\n',
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            app = _FakeHfss.instances[0]
            app.insert_segment_result = False
            runner.set_build_tasks({"2.5D Model": model_2d})

            with self.assertRaises(RuntimeError) as ctx:
                runner.run_build_tasks()

        self.assertIn("HFSS task `2.5D Model` failed", str(ctx.exception))
        self.assertIn("hfss.modeler.create_polyline().insert_segment", str(ctx.exception))
        self.assertIn("returned False", str(ctx.exception))

    def test_import_statements_are_rejected_before_execution(self) -> None:
        malicious = self._write_script(
            "bad_import.py",
            'import os\nhfss.record("should_not_run")\n',
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            runner.set_build_tasks({"Bad Import": malicious})

            with self.assertRaises(RuntimeError) as ctx:
                runner.run_build_tasks()

            app = _FakeHfss.instances[0]

        self.assertIn("Import", str(ctx.exception))
        self.assertEqual(app.events, [])

    def test_polyline_segment_helper_import_is_normalized_and_available(self) -> None:
        model_2d = self._write_script(
            "model_2d.py",
            "from ansys.aedt.core.modeler.cad.primitives import PolylineSegment\n"
            'profile = hfss.modeler.create_polyline(points=[[0, 0, 0], [1, 0, 0]], name="SlotProfile")\n'
            'profile.insert_segment(points=[[1, 0, 0], [0, 1, 0]], segment=PolylineSegment(segment_type="Spline", num_points=2))\n',
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            runner.set_build_tasks({"2.5D Model": model_2d})
            runner.run_build_tasks()

            app = _FakeHfss.instances[0]

        self.assertEqual(
            app.events[0],
            ("create_polyline", [[0, 0, 0], [1, 0, 0]], "SlotProfile"),
        )
        self.assertEqual(app.events[1][0], "insert_segment")
        self.assertIsInstance(app.events[1][3], _FakePolylineSegment)
        self.assertEqual(
            app.events[1][3].kwargs,
            {"segment_type": "Spline", "num_points": 2},
        )

    def test_windows_process_query_patch_replaces_pyaedt_powershell_lookup(self) -> None:
        fake_general = types.SimpleNamespace(_get_target_processes="original")
        fake_desktop = types.SimpleNamespace(_get_target_processes="original")
        fake_process = types.SimpleNamespace(
            info={
                "pid": 12345,
                "name": "ansysedt.exe",
                "cmdline": ["ansysedt.exe", "-grpcsrv", "50051"],
            }
        )
        fake_psutil = types.SimpleNamespace(
            process_iter=lambda _attrs: iter([fake_process]),
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
            ZombieProcess=RuntimeError,
        )

        def _fake_import(name: str):
            if name == "ansys.aedt.core.generic.general_methods":
                return fake_general
            if name == "ansys.aedt.core.desktop":
                return fake_desktop
            raise ImportError(name)

        with patch.object(hfss_runner_module.os, "name", "nt"), patch.dict(
            sys.modules, {"psutil": fake_psutil}
        ), patch(
            "leam.backends.hfss.tools.hfss_runner.importlib.import_module",
            side_effect=_fake_import,
        ):
            hfss_runner_module._patch_pyaedt_windows_process_query()

        self.assertTrue(fake_general._leam_psutil_process_query_patch)
        self.assertTrue(fake_desktop._leam_psutil_process_query_patch)
        self.assertIs(fake_general._get_target_processes, fake_desktop._get_target_processes)
        self.assertEqual(
            fake_general._get_target_processes(["ansysedt.exe"]),
            [(12345, ["ansysedt.exe", "-grpcsrv", "50051"])],
        )

    def test_compound_spline_patch_corrects_pyaedt_point_consumption(self) -> None:
        class _FakePatchedPolyline:
            def __init__(
                self,
                primitives,
                src_object=None,
                position_list=None,
                segment_type=None,
                cover_surface=False,
                close_surface=False,
                name=None,
                **_kwargs,
            ):
                self._positions = []
                self._segment_types = []
                self._is_covered = cover_surface
                self._is_closed = close_surface
                if isinstance(segment_type, list):
                    point_index = 0
                    for segment_index, segment in enumerate(segment_type):
                        if isinstance(segment, str):
                            segment = _FakePolylineSegment(segment)
                        self._segment_types.append(segment)
                        if segment_index == 0:
                            self._positions.append(list(position_list[0]))
                        if segment.type == "Line":
                            self._positions.extend(
                                [list(point) for point in position_list[point_index + 1 : point_index + 2]]
                            )
                            point_index += 1
                        elif segment.type == "Spline":
                            self._positions.extend(
                                [list(point) for point in position_list[: segment.num_points]]
                            )
                            point_index += segment.num_points - 1
                self.generated_positions = self._point_segment_string_array()

            def _point_segment_string_array(self):
                return [list(point) for point in self._positions]

            def _evaluate_arc_angle_extra_points(self, segment, start_point):
                segment.extra_points = [start_point, start_point]

        fake_polylines_module = types.SimpleNamespace(
            Polyline=_FakePatchedPolyline,
            PolylineSegment=_FakePolylineSegment,
        )

        def _fake_import(name: str):
            if name == hfss_runner_module._PYAEDT_POLYLINES_MODULE:
                return fake_polylines_module
            raise ImportError(name)

        points = [
            ["$x1", "20mm", "$ts"],
            ["$x2", "19mm", "$ts"],
            ["$x3", "18mm", "$ts"],
            ["$x4", "17mm", "$ts"],
            ["$x20", "1mm", "$ts"],
            ["$W_sub-$x20", "1mm", "$ts"],
            ["$W_sub-$x4", "17mm", "$ts"],
            ["$W_sub-$x3", "18mm", "$ts"],
            ["$W_sub-$x2", "19mm", "$ts"],
            ["$W_sub-$x1", "20mm", "$ts"],
            ["$x1", "20mm", "$ts"],
        ]
        segment_type = [
            _FakePolylineSegment(segment_type="Spline", num_points=5),
            _FakePolylineSegment(segment_type="Line"),
            _FakePolylineSegment(segment_type="Spline", num_points=5),
            _FakePolylineSegment(segment_type="Line"),
        ]

        with patch(
            "leam.backends.hfss.tools.hfss_runner.importlib.import_module",
            side_effect=_fake_import,
        ):
            hfss_runner_module._patch_pyaedt_compound_spline_polyline(
                types.SimpleNamespace(__version__="0.25.1")
            )

        polyline = _FakePatchedPolyline(
            primitives=object(),
            position_list=points,
            segment_type=segment_type,
            close_surface=False,
        )

        self.assertEqual(
            polyline.generated_positions,
            [
                ["$x1", "20mm", "$ts"],
                ["$x2", "19mm", "$ts"],
                ["$x3", "18mm", "$ts"],
                ["$x4", "17mm", "$ts"],
                ["$x20", "1mm", "$ts"],
                ["$W_sub-$x20", "1mm", "$ts"],
                ["$W_sub-$x4", "17mm", "$ts"],
                ["$W_sub-$x3", "18mm", "$ts"],
                ["$W_sub-$x2", "19mm", "$ts"],
                ["$W_sub-$x1", "20mm", "$ts"],
                ["$x1", "20mm", "$ts"],
            ],
        )
        self.assertEqual(polyline._positions, polyline.generated_positions)

    def test_open_builtin_is_rejected_before_execution(self) -> None:
        malicious = self._write_script(
            "bad_open.py",
            'open("pwned.txt", "w")\n',
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            runner.set_build_tasks({"Bad Builtin": malicious})

            with self.assertRaises(RuntimeError) as ctx:
                runner.run_build_tasks()

        self.assertIn("open", str(ctx.exception))

    def test_dunder_attribute_access_is_rejected_before_execution(self) -> None:
        malicious = self._write_script(
            "bad_attr.py",
            "hfss.__class__\n",
        )

        with self._patch_aedt_core():
            runner = HfssRunner(allow_unsafe_execution=True)
            runner.set_build_tasks({"Bad Attr": malicious})

            with self.assertRaises(RuntimeError) as ctx:
                runner.run_build_tasks()

        self.assertIn("dunder attribute access", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
