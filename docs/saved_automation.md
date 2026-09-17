# Saved Automation Evidence

`ableton_read_saved_automation` reads Arrangement automation from an explicit
absolute ALS path on local disk. It does not query Live, rewrite XML, recompress
the Set, or save current changes. Results describe the last saved file only.

Saved breakpoints, beat ranges and parameter references can help explain where
automation changes. Missing or unsupported fields remain unknown. Bar labels
assume a constant caller-supplied meter. Saved XML IDs are never Live runtime IDs
and must not be passed to write tools. Resolve current targets through the Hub.

For current automation activity use `ableton_scan_automation` or narrow parameter
state reads. Current state does not establish saved curve freshness. Ask the user
to save manually if fresh file evidence is required; never auto-save a song.

See `saved_als_reading.md` for the complete saved-file reader and source separation.
