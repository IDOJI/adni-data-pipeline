import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline/s7a_volume_workflow"))
import pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="adni runner ;$(unsafe) ")
        self.root = Path(self.temp.name)
        self.config = json.loads((Path(pipeline.__file__).with_name("config.example.json")).read_text())
        self.config["paths"] = {key: str(self.root / key) for key in pipeline.PATH_KEYS}
        self.config["fs_license"] = str(self.root / "license.txt")
        Path(self.config["fs_license"]).write_text("fake test license")
        self.run = self.config["runs"][0]
        bids = Path(self.config["paths"]["bids"])
        bids.mkdir()
        (bids / "dataset_description.json").write_text('{"Name":"Test","BIDSVersion":"1.10.0"}')
        self.session = bids / f"sub-{self.run['subject']}" / f"ses-{self.run['session']}"
        (self.session / "func").mkdir(parents=True)
        (self.session / "anat").mkdir()
        (self.session / "func" / "sub-999S9999_ses-20200101_task-rest_bold.nii").write_bytes(b"raw")
        (self.session / "anat" / "sub-999S9999_ses-20200101_T1w.nii").write_bytes(b"raw")
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.config))

    def tearDown(self):
        self.temp.cleanup()

    def test_visit_output_override_preserves_protocol_and_original_config(self):
        before = copy.deepcopy(self.config)
        selected = {**self.run, "paths": {"xcpd_output": str(self.root / "isolated_output"),
                                          "xcpd_work": str(self.root / "isolated_work")}}
        config, run = pipeline.configuration_for_run(self.config, selected)
        self.assertEqual(self.config, before)
        self.assertEqual(run, self.run)
        self.assertEqual(config["paths"]["fmriprep_output"], str(Path(before["paths"]["fmriprep_output"]).resolve()))
        command = pipeline.build_command(config, "xcpd", run)
        self.assertIn(f"type=bind,src={self.root.resolve() / 'isolated_output'},dst=/output", command)
        self.assertEqual(command[command.index("--fd-thresh") + 1], "0.5")
        self.assertEqual(config["postprocessing"], before["postprocessing"])

    def test_run_override_cannot_change_raw_input_or_overlap_it(self):
        for overrides in ({"bids": str(self.root / "other")},
                          {"xcpd_output": self.config["paths"]["bids"]}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(pipeline.PipelineError):
                    pipeline.configuration_for_run(self.config, {**self.run, "paths": overrides})

    def test_cli_dispatch_applies_selected_visit_paths(self):
        selected = self.config["runs"][1]
        selected["paths"] = {"xcpd_output": str(self.root / "case_output"),
                              "xcpd_work": str(self.root / "case_work")}
        self.config_path.write_text(json.dumps(self.config))
        with mock.patch.object(pipeline, "execute", return_value=0) as execute:
            code = pipeline.main(["--config", str(self.config_path), "run", "--stage", "xcpd",
                                  "--subject", selected["subject"]])
        self.assertEqual(code, 0)
        actual = execute.call_args.args
        self.assertEqual(actual[0]["paths"]["xcpd_output"], str((self.root / "case_output").resolve()))
        self.assertEqual(actual[3], {k: selected[k] for k in ("subject", "session")})

    def test_command_is_argv_and_input_readonly_even_with_shell_metacharacters(self):
        cmd = pipeline.build_command(self.config, "fmriprep", self.run)
        self.assertIsInstance(cmd, list)
        self.assertIn(f"type=bind,src={Path(self.config['paths']['bids']).resolve()},dst=/input,readonly", cmd)
        self.assertNotIn("--skip-bids-validation", cmd)
        self.assertNotIn("--sloppy", cmd)
        self.assertEqual(cmd[cmd.index("--use-syn-sdc") + 1], "error")
        self.assertEqual(cmd[cmd.index("--pull") + 1], "never")

    def test_path_overlap_and_symlink_alias_rejected(self):
        bad = copy.deepcopy(self.config)
        bad["paths"]["fmriprep_work"] = bad["paths"]["bids"] + "/work"
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_paths(bad)
        alias = self.root / "alias"
        alias.symlink_to(self.config["paths"]["bids"], target_is_directory=True)
        bad["paths"]["fmriprep_work"] = str(alias)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_paths(bad)

    def test_missing_subject_and_missing_session_rejected(self):
        with self.assertRaises(pipeline.PipelineError):
            pipeline.select_run(self.config, "absent")
        wrong = {**self.run, "session": "absent"}
        with self.assertRaises(pipeline.PipelineError):
            pipeline.check_inputs(self.config, "fmriprep", wrong)
        self.assertEqual(pipeline.select_run(self.config, "sub-999S9999", "ses-20200101"), self.run)

    def test_selected_input_mutation_detected_in_snapshot(self):
        bids = Path(self.config["paths"]["bids"])
        before = pipeline.snapshot_input(bids, self.run["subject"])
        file = next((self.session / "func").glob("*.nii"))
        file.write_bytes(b"changed")
        self.assertNotEqual(before, pipeline.snapshot_input(bids, self.run["subject"]))

    def test_lock_rejects_concurrent_execution(self):
        lock = self.root / "lock"
        pipeline.acquire_lock(lock)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.acquire_lock(lock)

    def test_xcpd_overrides_modes_and_uses_readonly_derivatives(self):
        cmd = pipeline.build_command(self.config, "xcpd", self.run)
        expected = {"--file-format": "nifti", "--dummy-scans": "auto", "--nuisance-regressors": "acompcor",
                    "--fd-thresh": "0.5", "--min-time": "240", "--despike": "n", "--combine-runs": "n"}
        for flag, value in expected.items():
            self.assertEqual(cmd[cmd.index(flag) + 1], value)

    @mock.patch("pipeline.subprocess.run")
    def test_resolve_image_uses_repository_digest(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps([{
            "Id": "sha256:imageid", "RepoDigests": ["nipreps/fmriprep@sha256:abcdef"],
            "Architecture": "amd64", "Os": "linux"}]), "")
        result = pipeline.resolve_image("nipreps/fmriprep:25.2.7")
        self.assertEqual(result["resolved"], "nipreps/fmriprep@sha256:abcdef")

    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_nonzero_exit_is_recorded_and_lock_released(self, docker, image):
        image.return_value = {"resolved": "nipreps/fmriprep@sha256:abc", "os": "linux", "architecture": "amd64"}
        docker.return_value = subprocess.CompletedProcess([], 17)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.execute(self.config, self.config_path, "fmriprep", self.run)
        logroot = Path(self.config["paths"]["logs"])
        record = json.loads(next(logroot.glob("*/run.json")).read_text())
        self.assertEqual(record["exit_code"], 17)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(record["input_unchanged"])
        self.assertFalse((logroot / "pipeline.lock").exists())
        self.assertNotIn("shell", docker.call_args.kwargs)

    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_repeated_runs_preserve_separate_provenance(self, docker, image):
        image.return_value = {"resolved": "nipreps/fmriprep@sha256:abc", "os": "linux", "architecture": "amd64"}
        docker.return_value = subprocess.CompletedProcess([], 0)
        for _ in range(2):
            pipeline.execute(self.config, self.config_path, "fmriprep", self.run)
        self.assertEqual(len(list(Path(self.config["paths"]["logs"]).glob("*/run.json"))), 2)

    def signature(self, config=None, stage="fmriprep", image=None, inputs=None):
        config = config or self.config
        image = image or {"resolved": "test/image@sha256:abc", "image_id": "sha256:id",
                          "os": "linux", "architecture": "amd64"}
        if inputs is None:
            inputs = pipeline.snapshot_input(Path(self.config["paths"]["bids"]), self.run["subject"])
        return pipeline.cache_signature(stage, pipeline.build_command(config, stage, self.run,
                                                                      image=image["resolved"]), image, inputs)

    def test_identical_cache_retry_preserves_signature_and_node_files(self):
        work = self.root / "cache"
        signature = self.signature()
        pipeline.guard_cache(work, signature)
        node = work / "node-result.pklz"
        node.write_bytes(b"preserve")
        signature_bytes = (work / pipeline.CACHE_SIGNATURE_NAME).read_bytes()
        pipeline.guard_cache(work, self.signature())
        self.assertEqual(node.read_bytes(), b"preserve")
        self.assertEqual((work / pipeline.CACHE_SIGNATURE_NAME).read_bytes(), signature_bytes)

    def test_unknown_nonempty_cache_rejected_without_adoption(self):
        work = self.root / "cache"
        work.mkdir()
        (work / "old-node").write_text("preserve")
        with self.assertRaisesRegex(pipeline.PipelineError, "new empty work directory"):
            pipeline.guard_cache(work, self.signature())
        self.assertFalse((work / pipeline.CACHE_SIGNATURE_NAME).exists())
        self.assertEqual((work / "old-node").read_text(), "preserve")

    def test_image_input_and_actual_stage_parameter_changes_rejected(self):
        original = self.signature()
        work = self.root / "cache"
        pipeline.guard_cache(work, original)
        changed_image = {"resolved": "test/image@sha256:new", "image_id": "sha256:new",
                         "os": "linux", "architecture": "amd64"}
        changed_config = copy.deepcopy(self.config)
        changed_config["random_seed"] += 1
        changes = [self.signature(image=changed_image), self.signature(config=changed_config),
                   self.signature(inputs={"changed.nii": {"bytes": 1, "sha256": "new"}})]
        for signature in changes:
            with self.subTest(identity=signature["sha256"]):
                with self.assertRaisesRegex(pipeline.PipelineError, "Cache identity changed"):
                    pipeline.guard_cache(work, signature)
        self.assertEqual(json.loads((work / pipeline.CACHE_SIGNATURE_NAME).read_text()), original)

    def test_other_stage_audit_config_and_runner_source_do_not_change_signature(self):
        original = self.signature()
        changed = copy.deepcopy(self.config)
        changed["postprocessing"]["maximum_censored_fraction"] = .2
        changed["postprocessing"]["smoothing_fwhm_mm"] = 8
        changed["images"]["xcpd"] = "unrelated/image:next"
        changed["runs"][1]["subject"] = "OTHER"
        changed["paths"]["logs"] = str(self.root / "new_logs")
        with mock.patch.object(pipeline, "RUNNER_SOURCE", b"different non-semantic runner source"):
            self.assertEqual(self.signature(config=changed), original)
        xcp_original = self.signature(stage="xcpd")
        changed = copy.deepcopy(self.config)
        changed["postprocessing"]["maximum_censored_fraction"] = .2
        self.assertEqual(self.signature(config=changed, stage="xcpd"), xcp_original)
        changed["postprocessing"]["fd_threshold_mm"] = .4
        self.assertNotEqual(self.signature(config=changed, stage="xcpd"), xcp_original)

    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_unknown_cache_prevents_docker_and_preserves_failure_log(self, docker, image):
        image.return_value = {"resolved": "nipreps/fmriprep@sha256:abc", "os": "linux", "architecture": "amd64"}
        work = Path(self.config["paths"]["fmriprep_work"]) / f"sub-{self.run['subject']}" / f"ses-{self.run['session']}"
        work.mkdir(parents=True)
        (work / "node-result").write_text("old")
        with self.assertRaisesRegex(pipeline.PipelineError, "no cache signature"):
            pipeline.execute(self.config, self.config_path, "fmriprep", self.run)
        docker.assert_not_called()
        logroot = Path(self.config["paths"]["logs"])
        record = json.loads(next(logroot.glob("*/run.json")).read_text())
        self.assertEqual(record["status"], "failed")
        self.assertFalse((logroot / "pipeline.lock").exists())

    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_source_and_citations_captured_even_after_failed_container(self, docker, image):
        image.return_value = {"resolved": "nipreps/fmriprep@sha256:abc", "os": "linux", "architecture": "amd64"}
        output = Path(self.config["paths"]["fmriprep_output"])
        relative_paths = [Path("logs/CITATION.md"),
                          Path(f"sub-{self.run['subject']}/log/attempt/CITATION.bib"),
                          Path(f"sub-{self.run['subject']}/ses-{self.run['session']}/logs/CITATION.tex")]
        for path in relative_paths:
            (output / path).parent.mkdir(parents=True, exist_ok=True)
            (output / path).write_text(str(path))
        unrelated = output / "sub-OTHER/logs/CITATION.md"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("must not copy")
        frozen_source = b"# source bytes captured when invocation started\n"
        def finish(*args, **kwargs):
            # A concurrent code deployment must not alter the saved source.
            pipeline.RUNNER_SOURCE = b"new deployed source"
            return subprocess.CompletedProcess([], 17)
        docker.side_effect = finish
        with mock.patch.object(pipeline, "RUNNER_SOURCE", frozen_source):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.execute(self.config, self.config_path, "fmriprep", self.run)
        record_path = next(Path(self.config["paths"]["logs"]).glob("*/run.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual((record_path.parent / "runner_source.py").read_bytes(), frozen_source)
        self.assertEqual(record["runner_sha256"], hashlib.sha256(frozen_source).hexdigest())
        self.assertEqual(len(record["citation_snapshots"]), 3)
        for entry in record["citation_snapshots"]:
            copy_path = record_path.parent / entry["copied_to"]
            self.assertEqual(entry["sha256"], pipeline.sha256(copy_path))
            self.assertEqual(copy_path.read_bytes(), Path(entry["source"]).read_bytes())
        # Later global citation overwrites do not change this attempt's copy.
        (output / "logs/CITATION.md").write_text("next subject")
        self.assertEqual((record_path.parent / "citations/logs/CITATION.md").read_text(), "logs/CITATION.md")

    def test_nifti_header_shape(self):
        path = self.root / "test.nii"
        header = bytearray(352)
        struct.pack_into("<i", header, 0, 348)
        struct.pack_into("<8h", header, 40, 4, 2, 3, 4, 20, 1, 1, 1)
        path.write_bytes(header)
        self.assertEqual(pipeline.nifti_shape(path), [2, 3, 4, 20])

    def prepare_xcpd_inputs(self):
        root = Path(self.config["paths"]["fmriprep_output"])
        func = root / f"sub-{self.run['subject']}" / f"ses-{self.run['session']}" / "func"
        func.mkdir(parents=True)
        (root / "dataset_description.json").write_text('{"Name":"Test derivatives"}')
        (func / (f"sub-{self.run['subject']}_ses-{self.run['session']}_task-rest_"
                 "space-MNI152NLin2009cAsym_res-2_desc-preproc_bold.nii")).write_bytes(b"input")

    def save_execution(self, stamp="2026-10-28T01:00:00+00:00", **changes):
        root = Path(self.config["paths"]["logs"])
        label = stamp.replace(":", "").replace("+", "")
        folder = root / f"{label}_xcpd_sub-{self.run['subject']}_ses-{self.run['session']}_test"
        folder.mkdir(parents=True, exist_ok=True)
        record = {"started_at": stamp, "stage": "xcpd", "run": self.run,
                  "status": "execution_completed_qc_required", "exit_code": 0,
                  "input_unchanged": True, "config": self.config}
        record.update(changes)
        path = folder / "run.json"
        path.write_text(json.dumps(record))
        return path

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_xcpd_success_runs_repair_and_captures_frozen_sources(self, docker, image, repair):
        self.prepare_xcpd_inputs()
        image.return_value = {"resolved": "pennlinc/xcp_d@sha256:abc", "os": "linux", "architecture": "amd64"}
        repair.return_value = {"status": "applied", "payload_unchanged": True}
        runner_source, helper_source = b"original runner\n", b"original helper\n"
        replacement = mock.Mock(side_effect=AssertionError("newly deployed helper must not run"))
        def container_finished(*args, **kwargs):
            pipeline.RUNNER_SOURCE = b"replacement runner"
            pipeline.xcpd_metadata.SOURCE_BYTES = b"replacement helper"
            pipeline.xcpd_metadata.repair_run = replacement
            return subprocess.CompletedProcess([], 0)
        docker.side_effect = container_finished
        with mock.patch.object(pipeline, "RUNNER_SOURCE", runner_source), \
                mock.patch.object(pipeline.xcpd_metadata, "SOURCE_BYTES", helper_source):
            self.assertEqual(pipeline.execute(self.config, self.config_path, "xcpd", self.run), 0)
        paths = pipeline.validate_paths(self.config)
        repair.assert_called_once_with(paths["xcpd_output"], self.run["subject"], self.run["session"],
                                       paths["logs"] / "metadata_repairs", apply=True)
        replacement.assert_not_called()
        path = next(paths["logs"].glob("*/run.json"))
        record = json.loads(path.read_text())
        self.assertEqual(record["status"], "execution_completed_qc_required")
        self.assertEqual(record["runner_version"], "1.3.0")
        self.assertEqual(record["metadata_repair"]["status"], "completed")
        self.assertTrue(record["metadata_repair"]["result"]["payload_unchanged"])
        self.assertEqual((path.parent / record["runner_source"]).read_bytes(), runner_source)
        helper = record["metadata_repair_source"]
        self.assertEqual((path.parent / helper["path"]).read_bytes(), helper_source)
        self.assertEqual(helper["sha256"], hashlib.sha256(helper_source).hexdigest())

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_xcpd_repair_failure_marks_successful_container_run_failed(self, docker, image, repair):
        self.prepare_xcpd_inputs()
        image.return_value = {"resolved": "pennlinc/xcp_d@sha256:abc", "os": "linux", "architecture": "amd64"}
        docker.return_value = subprocess.CompletedProcess([], 0)
        repair.side_effect = pipeline.xcpd_metadata.RepairError("payload verification failed")
        with self.assertRaisesRegex(ValueError, "payload verification"):
            pipeline.execute(self.config, self.config_path, "xcpd", self.run)
        paths = pipeline.validate_paths(self.config)
        record = json.loads(next(paths["logs"].glob("*/run.json")).read_text())
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["exit_code"], 0)  # Docker exit is preserved.
        self.assertEqual(record["pipeline_exit_code"], 1)
        self.assertEqual(record["metadata_repair"]["status"], "failed")
        self.assertIn("payload verification", record["metadata_repair"]["error"])
        self.assertTrue(record["input_unchanged"])
        self.assertFalse((paths["logs"] / "pipeline.lock").exists())
        self.assertFalse(pipeline.xcpd_run_lock(paths, self.run).exists())

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    @mock.patch("pipeline.resolve_image")
    @mock.patch("pipeline.subprocess.run")
    def test_xcpd_container_failure_never_calls_repair(self, docker, image, repair):
        self.prepare_xcpd_inputs()
        image.return_value = {"resolved": "pennlinc/xcp_d@sha256:abc", "os": "linux", "architecture": "amd64"}
        docker.return_value = subprocess.CompletedProcess([], 23)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.execute(self.config, self.config_path, "xcpd", self.run)
        repair.assert_not_called()
        path = next(Path(self.config["paths"]["logs"]).glob("*/run.json"))
        record = json.loads(path.read_text())
        self.assertEqual(record["exit_code"], 23)
        self.assertEqual(record["status"], "failed")
        self.assertNotIn("metadata_repair", record)
        self.assertTrue((path.parent / record["metadata_repair_source"]["path"]).is_file())

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    def test_finalize_preserves_execution_and_uses_only_selected_lock(self, repair):
        repair.return_value = {"status": "already_valid_no_op"}
        source = self.save_execution()
        source_bytes = source.read_bytes()
        paths = pipeline.validate_paths(self.config)
        global_lock = paths["logs"] / "pipeline.lock"
        global_lock.write_text("other subject is running")
        self.assertEqual(pipeline.finalize_xcpd(self.config, self.config_path, self.run), 0)
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(global_lock.read_text(), "other subject is running")
        self.assertFalse(pipeline.xcpd_run_lock(paths, self.run).exists())
        path = next((paths["logs"] / "metadata_finalizations").glob("*/finalization.json"))
        record = json.loads(path.read_text())
        self.assertEqual(record["status"], "metadata_finalization_completed_qc_required")
        self.assertEqual(record["source_run_sha256"], hashlib.sha256(source_bytes).hexdigest())
        self.assertEqual((path.parent / record["source_run_snapshot"]).read_bytes(), source_bytes)
        self.assertEqual((path.parent / record["runner_source"]).read_bytes(), pipeline.RUNNER_SOURCE)
        self.assertEqual((path.parent / record["metadata_repair_source"]["path"]).read_bytes(),
                         pipeline.xcpd_metadata.SOURCE_BYTES)
        repair.assert_called_once()

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    def test_finalize_refuses_latest_failed_running_or_changed_input_not_older_success(self, repair):
        self.save_execution()
        changes = [{"status": "failed"}, {"status": "running"}, {"exit_code": 7},
                   {"input_unchanged": False}, {"input_unchanged": None}]
        for change in changes:
            with self.subTest(change=change):
                self.save_execution("2026-10-28T02:00:00+00:00", **change)
                with self.assertRaisesRegex(pipeline.PipelineError, "Latest selected XCP-D attempt"):
                    pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        repair.assert_not_called()

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    def test_finalize_failure_records_failure_without_rewriting_run(self, repair):
        source = self.save_execution()
        source_bytes = source.read_bytes()
        repair.side_effect = pipeline.xcpd_metadata.RepairError("conflicting TR")
        with self.assertRaisesRegex(ValueError, "conflicting TR"):
            pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        logroot = Path(self.config["paths"]["logs"])
        record = json.loads(next((logroot / "metadata_finalizations").glob("*/finalization.json")).read_text())
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["exit_code"], 1)
        self.assertEqual(record["metadata_repair"]["status"], "failed")
        self.assertEqual(source.read_bytes(), source_bytes)

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    @mock.patch("pipeline.subprocess.run")
    def test_selected_output_lock_blocks_execute_and_finalize_without_removing_other_lock(self, docker, repair):
        self.prepare_xcpd_inputs()
        self.save_execution()
        paths = pipeline.validate_paths(self.config)
        lock = pipeline.xcpd_run_lock(paths, self.run)
        lock.write_text("existing selected writer")
        with self.assertRaises(pipeline.PipelineError):
            pipeline.execute(self.config, self.config_path, "xcpd", self.run)
        self.assertEqual(lock.read_text(), "existing selected writer")
        with self.assertRaises(pipeline.PipelineError):
            pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        self.assertEqual(lock.read_text(), "existing selected writer")
        self.assertFalse((paths["logs"] / "pipeline.lock").exists())
        docker.assert_not_called()
        repair.assert_not_called()

    def test_finalize_cli_requires_xcpd_stage(self):
        with self.assertRaises(SystemExit) as error:
            pipeline.main(["finalize-xcpd", "--stage", "fmriprep", "--subject", self.run["subject"]])
        self.assertEqual(error.exception.code, 2)

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    def test_finalize_rejects_absent_history_and_different_output(self, repair):
        with self.assertRaisesRegex(pipeline.PipelineError, "No selected XCP-D"):
            pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        different = copy.deepcopy(self.config)
        different["paths"]["xcpd_output"] = str(self.root / "different_output")
        self.save_execution(config=different)
        with self.assertRaisesRegex(pipeline.PipelineError, "different output directory"):
            pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        repair.assert_not_called()

    @mock.patch("pipeline.xcpd_metadata.repair_run")
    def test_finalize_detects_legacy_record_change_before_repair(self, repair):
        source = self.save_execution()
        latest = pipeline.latest_completed_xcpd_run
        calls = 0
        def change_before_second_check(paths, run):
            nonlocal calls
            calls += 1
            if calls == 2:
                value = json.loads(source.read_text())
                value["status"] = "running"
                source.write_text(json.dumps(value))
            return latest(paths, run)
        with mock.patch.object(pipeline, "latest_completed_xcpd_run", side_effect=change_before_second_check):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.finalize_xcpd(self.config, self.config_path, self.run)
        repair.assert_not_called()
        self.assertEqual(json.loads(source.read_text())["status"], "running")
        root = Path(self.config["paths"]["logs"]) / "metadata_finalizations"
        record = json.loads(next(root.glob("*/finalization.json")).read_text())
        self.assertEqual(record["status"], "failed")


if __name__ == "__main__":
    unittest.main()
