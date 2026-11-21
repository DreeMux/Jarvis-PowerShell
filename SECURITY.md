# Security Policy

## Supported versions

Only the latest release (the 3.3.x line) receives fixes. Older versions are kept
in this repository for history only.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Use GitHub's private reporting instead: open the **Security** tab of this
repository and choose **Report a vulnerability**. Describe what you found, which
version you used and, if you can, how to reproduce it.

This is a small hobby project, so replies may take a few days. Reports that
include a clear way to reproduce the problem are the easiest to fix.

## Things worth knowing about this project

- Jarvis is read-only by default. It only writes, moves or starts things when
  you ask (updating itself, starting a game or a program, saving a report).
- **Screen Watch** (Windows only) reads session, connection, process and window
  information. By default its shield ends Firefox at once, without asking you to
  save. Change it with `watch shield hide` or `watch shield off`.
- The **Claude Code bridge** is on by default: text Jarvis cannot answer
  locally is sent to Claude Code, and so leaves your computer. Turn it off with
  `claude off`.
- The self-update (`implement jarvis`) runs 9 checks, makes a backup and rolls
  back on failure.
