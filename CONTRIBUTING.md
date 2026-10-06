# Contributing

Thank you for helping improve CallPerch for Linux.

## Report a problem

For app support, use [CallPerch support](https://github.com/donrad64/callperch-support/issues/new/choose). Code and build issues may be opened in this repository. Include the version, distribution, architecture, reproduction steps, and expected/actual behavior. Use synthetic records; do not attach live FCC databases, personal addresses, real FRNs, private logs, or credentials. Report vulnerabilities privately as described in SECURITY.md.

## Propose a change

1. Fork this repository and create a focused branch.
2. Set up the environment described in README.md.
3. Make the smallest change that addresses the problem. Keep FCC estimates and historical summaries qualified; avoid inferring personal intent from licensing records.
4. Run backend and Qt UI tests. Add meaningful regression coverage for behavior changes. Do not download FCC archives in automated tests.
5. Open a pull request explaining the problem, resulting behavior, validation, and relevant limitations. Include synthetic-data screenshots for visual changes.

Use an isolated `XDG_DATA_HOME` when manually testing imports or deletion so your personal database is unaffected. Test desktop behavior in both Light and Dark appearances when appropriate. Native packages must be built on Linux; offscreen tests cannot verify notification delivery or every display server.

## License and review

By submitting a contribution, you agree to license it under this repository's MIT license and confirm you have the right to contribute it. Third-party code and assets must keep their applicable notices. Maintainers review changes before merging. Automated checks run with read-only permissions and do not publish releases.
