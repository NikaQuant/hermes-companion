# Controlled file inbox

## Design goal

Companion does not expose arbitrary server filesystem browsing. Users upload into a profile-specific managed inbox, and the bridge decides the final path.

```text
client upload
   ↓
request/body limit
   ↓
extension + size validation
   ↓
randomized managed filename
   ↓
SHA-256 + optional scanner
   ↓
profile/user database record
```

## Default supported extensions

```text
.txt .md .csv .tsv .json .jsonl .yaml .yml .toml
.py .js .mjs .cjs .ts .tsx .jsx .html .css .sql .xml
.log .ini .cfg .mq5 .mqh .set
.pdf .png .jpg .jpeg .webp .gif
```

The operator can narrow or extend the list with `UPLOAD_ALLOWED_EXTENSIONS`. Extension allowlisting is not content validation; use a malware scanner for hostile files.

## Limits

| Setting | Default |
|---|---:|
| `MAX_UPLOAD_BYTES` | 25 MiB |
| `UPLOAD_RETENTION_DAYS` | 30 days |
| `UPLOAD_SCAN_TIMEOUT_SECONDS` | 30 seconds |
| global `MAX_REQUEST_BODY_BYTES` | 2 MiB for ordinary routes; upload route streams under its own limit |

## Optional scanner

`UPLOAD_SCAN_COMMAND` is parsed into an executable and fixed arguments. The staged file path is appended as the last argument.

Windows Defender example:

```text
UPLOAD_SCAN_COMMAND="C:\Program Files\Windows Defender\MpCmdRun.exe" -Scan -ScanType 3 -File
```

Confirm the exact Defender command line on the target Windows version before relying on it operationally.

A non-zero scanner exit rejects the upload and removes the staged file.

## Isolation

Uploads are separated by user and profile. Database lookups enforce the owner and profile. Download and delete routes do not accept arbitrary paths.

The optional live gateway permits `image.attach`, `pdf.attach` and `file.attach` only when the path resolves inside the authenticated user's managed upload directory for the selected profile.

## Retention

Startup housekeeping removes expired upload records and files according to `UPLOAD_RETENTION_DAYS`. Administrators should also monitor disk usage and include uploads in a disaster backup only when required.

## Privacy

File names, hashes, size and ownership metadata are stored in the Companion database. File contents are not placed in the audit log or diagnostics bundle.
