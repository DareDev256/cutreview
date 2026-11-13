# Security

Cut Review runs on your own machine. It has no server and no account, and it makes no network request.

## What it touches

- **Reads** the FCPXML files and notes files you name. FCPXML is parsed through fcp-mcp-server's `safe_parse` (defusedxml), so external entities and entity expansion are refused.
- **Runs `ffmpeg`**, when it is on the path, to take before and after frames from media files the FCPXML names. Only a file that exists on this machine is read, the command is an argument list (never a shell), and frames are written to a cache folder. `--no-frames` turns this off.
- **Writes** the marked FCPXML (and a JSON ledger) next to the cut, and each HTML page where you ask. The MCP tool refuses to write anywhere outside the folder of the cut it was given.
- **HTML pages** escape every note and clip name, and load nothing from the network: no script, font or stylesheet from anywhere else.

## What it is not designed for

It trusts the files you give it to be your own projects. It is not a sandbox for hostile media: `ffmpeg` decodes whatever media file the FCPXML points at, with ffmpeg's own security posture.

## Reporting a vulnerability

Use GitHub's private reporting on this repository (Security, then Report a vulnerability). Please do not open a public issue for a security problem.
