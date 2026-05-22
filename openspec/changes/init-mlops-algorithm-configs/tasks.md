## 1. Bootstrap data source setup

- [x] 1.1 Create `server/apps/mlops/support-files/algorithm-configs/` with supported `algorithm_type` subdirectories covering all six supported algorithm types.
- [x] 1.2 Add the first verification batch of default `<name>.json` files for one selected algorithm type using the agreed top-level contract: `name`, `display_name`, `image`, `scenario_description`, and `form_config`.
- [x] 1.3 Review the default JSON files to ensure each file name stem matches its `name` field exactly, each file stays within the supported `algorithm_type` directory, and no unknown top-level fields are present.
- [x] 1.4 After verification passes, add the remaining default algorithm JSON files for the other supported algorithm types.

## 2. Implement the MLOPS bootstrap command

- [x] 2.1 Add `server/apps/mlops/management/commands/init_algorithm_config.py` as the new bootstrap management command.
- [x] 2.2 Implement directory scanning so the command only reads direct `.json` files under supported `algorithm_type` directories and ignores non-JSON files and deeper paths.
- [x] 2.3 Implement file validation for JSON parsing, top-level object shape, required fields, unknown fields, `form_config` object type, and `name`/filename consistency.
- [x] 2.4 Implement first-write initialization logic using `(algorithm_type, name)` so missing records are created and existing records are skipped without updates.
- [x] 2.5 Implement command output for per-file invalid reasons, plus final `created / skipped_existing / skipped_invalid` summary reporting and `mlops_logger` lifecycle logging.

## 3. Integrate with batch initialization

- [x] 3.1 Update `server/apps/core/management/commands/batch_init.py` to add an `_init_mlops()` step that calls `init_algorithm_config`.
- [x] 3.2 Add `mlops` to the default `batch_init` app list so the default initialization flow runs the algorithm config bootstrap command.
- [x] 3.3 Ensure MLOPS bootstrap failures at the file level do not abort the overall batch initialization flow.

## 4. Verify bootstrap behavior

- [x] 4.1 Run the bootstrap command in a clean state and verify valid JSON files create `AlgorithmConfig` records.
- [x] 4.2 Run the bootstrap command again and verify existing `(algorithm_type, name)` records are skipped without overwriting data.
- [x] 4.3 Verify invalid JSON files and unknown top-level fields are reported through command output while other valid files in the same run still import successfully.
- [x] 4.4 Verify the batch initialization flow invokes the MLOPS bootstrap command when `mlops` is included.
