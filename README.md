# AutoRejection Data Validation

AutoRejection is a Python-based batch validation utility for delimited data files. It reads a root configuration file plus one or more file-specific metadata configurations, validates each input row in chunks, writes clean rows to a temporary validated file, writes rejected rows with error details to a reject file, and appends a processing summary for each run.

The current sample configuration is designed for the Asia `cf1` customer data pack, using tab-delimited `.prod` files and Windows-style CRLF row endings.

## What this project does

- Loads a shared/root JSON configuration and expands one or more pack configuration files with a glob pattern.
- Detects source file encoding automatically when the pack configuration does not provide one.
- Processes large files in chunks with Python multiprocessing.
- Validates each row against file-specific column metadata:
  - expected column count
  - maximum string length
  - numeric values when a column is configured as `numeric`
  - date values using either the default date regex or a column-specific `date_format`
- Preserves the configured column delimiter and row delimiter in generated output files.
- Writes rejected rows to timestamped reject files with row and column error details.
- Writes run statistics to a summary file.
- Replaces the original input file with the validated clean file when validation errors are found.

## Repository layout

```text
.
├── config/
│   └── asia/
│       ├── root-config.json          # Shared paths, delimiters, extension, chunk size
│       └── cf1/
│           ├── config-customer.json
│           ├── config-customerSalesRep.json
│           ├── config-customeraddress.json
│           ├── config-customerclass.json
│           └── config-customerprofile.json
├── scripts/
│   └── auto_validate.py              # Main validation script
├── validator-cf1.cmd                 # Windows command wrapper for the Asia cf1 pack
└── info.txt                          # Development notes and validation backlog
```

## Requirements

- Python 3.10 or later is recommended.
- Python package:
  - `charset-normalizer`

Install the dependency with:

```bash
pip install charset-normalizer
```

> Tip: create and activate a virtual environment before installing dependencies if you are running this outside a controlled batch server.

## Configuration model

AutoRejection uses two configuration layers.

### 1. Root configuration

The root configuration defines shared input/output paths and default file formatting. The sample root configuration is located at:

```text
config/asia/root-config.json
```

Important fields:

| Field | Purpose |
| --- | --- |
| `input_path` | Folder containing source files to validate. |
| `validate_path` | Folder where temporary clean/validated files are written. |
| `reject_path` | Folder where timestamped reject files are written. |
| `summary_path` | Folder where summary files are appended. |
| `column_delimiter` | Default column delimiter, for example `\t`. |
| `row_delimiter` | Default row delimiter, for example `\r\n`. |
| `file_extension` | File extension appended to each configured `file_name`. |
| `chunk_size` | Number of rows to validate per chunk. |
| `endcoding` | Default encoding value used by the existing configuration. |
| `meta` | Runtime-populated list of pack configurations. |

### 2. Pack/file configuration

Pack configuration files define the validation metadata for each data file. The Asia `cf1` examples are located at:

```text
config/asia/cf1/config-*.json
```

Important fields:

| Field | Purpose |
| --- | --- |
| `file_name` | Base filename. The script appends the root `file_extension`. |
| `column_delimiter` | Optional file-level delimiter override. |
| `row_delimiter` | Optional file-level row delimiter override. |
| `header_row` | Header row number to skip during validation. Use `0` when there is no header row to skip. |
| `endcoding` | Optional file encoding override. If absent, encoding is detected automatically. |
| `columns` | Object keyed by zero-based column index. Each value describes the expected column. |

Column metadata supports:

| Field | Purpose |
| --- | --- |
| `name` | Human-readable column name used in reject messages. |
| `type` | Column type used by validation logic. Current script validation handles `string`, `numeric`, and `date`. |
| `max_length` | Maximum allowed length for text values. |
| `date_format` | Optional regular expression for date validation. |
| `precision` / `scale` | Present in some configs as decimal metadata for downstream compatibility. |

## How to run

From the repository root, run the validator with a root configuration path and a pack configuration glob:

```bash
python scripts/auto_validate.py config/asia/root-config.json "config/asia/cf1/config-*.json"
```

On Windows, you can adapt the included command wrapper:

```bat
validator-cf1.cmd
```

Before running, update the paths in `config/asia/root-config.json` so they match your local or server folders.

## Output behavior

For each pack configuration, the script builds file paths as follows:

- input file: `{input_path}{file_name}{file_extension}`
- validated file: `{validate_path}{file_name}{file_extension}`
- reject file: `{reject_path}{file_name}-{timestamp}_reject.txt`
- summary file: `{summary_path}{file_name}.summary.txt`

When errors are found:

1. Clean rows are written to the validated output file.
2. Error rows are written to a timestamped reject file.
3. The validated file replaces the original input file.
4. A summary entry is appended with total, valid, and rejected row counts.

When no errors are found:

1. Temporary validated and reject files are removed.
2. A summary entry is appended.

## Reject file format

Rejected rows are written with an additional first column containing one or more validation messages, followed by the original row values. Example message patterns include:

```text
Errors: Row 10, Column CustomerName_LB length overflow (361)
Errors: Row 24, Column ExtractionDate_DT invalid date format: 1900-01-01 00:00:00.000
Errors: Row 42,Column count mismatch: 35
```

## Adding a new file validation config

1. Create a new JSON file under the relevant pack folder, for example:

   ```text
   config/asia/cf1/config-newfile.json
   ```

2. Set `file_name` to the base name of the input file without extension.
3. Add every expected column under `columns`, using zero-based indexes as keys.
4. Set `type`, `max_length`, and `date_format` where needed.
5. Run the validator with the existing pack glob so the new file is included.

## Operational notes

- The script is intended for batch processing and prints start/progress/done messages to standard output.
- Existing paths in the sample configuration are Windows absolute paths. Change them before running in a new environment.
- Keep reject and summary folders separate from source input folders so operational output does not get reprocessed accidentally.
- Use a conservative `chunk_size` if running on a machine with limited memory; increase it only after testing with representative files.
- The development notes in `info.txt` include future work such as additional numeric formats, config generation, email attachments, and performance testing.

## Known implementation notes

- Some configuration files use `integer` or `decimal` types, while the current numeric validation branch checks the value `numeric`. If you need strict integer/decimal validation, update the validator logic or normalize config type names before production use.
- The configuration key is currently spelled `endcoding` in existing JSON files and script logic. Keep that spelling unless the script and configs are updated together.

