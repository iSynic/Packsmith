# Packsmith preview worker interface

The Qt controller starts a new `workers/packsmith-worker.exe` for each job. ZIP/7z use the packaged 7-Zip 26.03 `7z.dll` SDK interfaces. Legacy extensions (`.sit`, `.hqx`, `.sitx`, `.bin`) or explicit `engine:"xad"` route through the decoder-only `workers/legacy/xad-stream.exe`. The filesystem-owning Qt worker receives one UTF-8 JSON object followed by a newline on stdin; later lines may send `{"cancel":true}`. Passwords are optional fields in that first object and reach the decoder through another private pipe. Arguments, stderr, GUI recovery journals and build/test logs never contain user passwords.

This is a private preview contract. Version negotiation, explicit capabilities negotiation, richer typed errors and bounded queue backpressure remain interface work before third-party backend integration.

| Operation | Request fields | Result |
|---|---|---|
| `list` | `archive`, optional `password` | Batches of at most 500 `items`; final entry count, format and archive SHA-256 `fingerprint` |
| `extract` | `archive`, `destination`, optional numeric `ids`, `password`, `fingerprint` | Fresh committed output directory and mapping-file name; folders include descendants; empty IDs mean all entries |
| `test` | `archive`, optional `password`, `fingerprint` | Integrity result with no destination files |
| `create` | `archive`, `format` (`zip`/`7z`), array of absolute source `files`, optional `password` | A new archive; an existing target is rejected |
| `update` | `archive`, optional `files`, `remove` IDs, `rename` objects (`id`,`path`), `replace` objects (`id`,`source`), `password`, `fingerprint` | Verified replacement and retained original backup; folder edits include descendants |
| `cleanup` | Exact staging `path`, original `parent`, job `token` | Removal of an interrupted job's staging directory after containment and ownership-marker checks |

Responses are UTF-8 JSON lines. Events are `entries`, `progress`, `staging`, `complete`, `error`, `cancelled`, `warning`, `cleanup_failed` and `recovery_required`. Sizes and progress byte counters are decimal strings, preserving 64-bit values. Entry indices are numeric IDs scoped to a particular archive fingerprint. Names use `/` for display; extraction plans their Windows representation separately. A caller must wait for worker exit before starting another job in that process slot.

Progress is throttled to approximately 10 events/second. Cooperative cancellation is checked in stream reads, writes, hash loops and SDK callbacks. The GUI sends cancellation first, then kills the helper after three seconds if necessary. Exit status zero plus `complete` means success; other statuses or a missing terminal event mean failure. Archive errors retain readable engine result information. The current error contract does not yet classify every filesystem/codec failure with a distinct machine-readable code.

The worker reports staging ownership before payload writes. The GUI atomically journals only the path, parent and random token in its application data directory. It invokes a separate cleanup helper after a crash or on the next launch. Cleanup refuses a different parent/token and never traverses reparse-point directories. Ambiguous `ReplaceFileW` failures mark a journal for manual review and retain replacement/backup candidates; they are not automatically pruned.

Replacement verification decodes and hashes all payloads, checks entry count/path/type, then protects the original against writes until the Windows replacement call. Renames request existing metadata from the SDK. This is not a guarantee that every opaque extra field, platform attribute or filename-encoding representation survives an edit; broad metadata qualification is still required.

## Legacy adapter

The XAD route permits only `list`, `extract` and `test`. Listing completion includes `engine:"xad"`, `read_only:true`, `format`, count and archive fingerprint. Rows add `components`, `absolute`, `has_data`, `has_resource`, decimal-string `resource_size`, base64 `finder_info` and `raw_name`, `encoding` and optional `modified_ms`. Classic names default to Mac Roman; an optional `filename_encoding` override applies consistently to listing and extraction. This preview routes `.sitx` to XAD but does not qualify StuffIt X without realistic fixtures.

The decoder accepts protocol 1, `list`/`stream`/`test`, archive, optional password, filename encoding and numeric IDs. It receives no destination and performs no extraction writes. It emits batched metadata, `ready`, then `begin`/base64 `chunk`/`end` frames for data/resource streams, `verified` per logical entry, and a terminal result. Fork chunks are at most 64 KiB before base64. Selected directories include descendants. Supported BinHex/MacBinary archive wrappers are expanded; their streams are checksum-checked, but wrapper bytes/metadata are not extracted alongside the inner files. Other recognized embedded archive formats remain decoded wrapper payloads rather than using an unqualified fork-pairing adapter.

The owning worker locks/fingerprints the source, plans collisions jointly for data and `._` names, rejects unsafe components and links, writes to protected staging, and checks stream identities, extents and completed fork sets. A resource-only file receives an empty data file. A checksum failure prevents committing any output folder. The mapping records data/resource SHA-256 separately from AppleDouble container bytes, raw names, decoded components, encoding and interpreted modification time. Literal slash/backslash/colon characters inside a Mac filename are encoded rather than treated as filesystem separators.

A Windows kill-on-close job owns the decoder before it receives its request; forced termination of the owning worker also terminates decoding. Cancellation is forwarded and escalates after 2.5 seconds. The existing staging journal/recovery worker handles partial output. This protocol is an internal implementation seam, not complete capability negotiation or a security sandbox.

Legacy completion and extraction mappings include `checksum_coverage` with `checked_forks`, `unchecked_forks` and `expanded_wrappers`. The counts include wrapper streams. Individual mapped fork hashes also record whether a source checksum was checked. A successful decode with unchecked streams is reported with that limitation; hashing decoded bytes alone does not verify an absent source checksum.
