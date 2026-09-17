# Versioning and publishing

[Back to README](../README.md)

`.github/workflows/build.yml` builds and tests on pushes to `main` (excluding
documentation-only changes), on published GitHub releases, and on manual runs.
Publishing a GitHub release publishes its tagged code to PyPI after all tests
and build steps succeed. Pushes and manual workflow runs only create CI artifacts.
Saving a draft release does not publish; publishing a prerelease also triggers
the workflow.

Before publishing a new version, update `version` in `pyproject.toml`,
`__version__` in `src/pygrbl_streamer/__init__.py`, the README version and
`CHANGELOG.md`; refresh `uv.lock` with `uv lock`.
The workflow does not increment versions or skip existing PyPI files.

To publish 1.0.0:

1. Commit and push the version changes and workflow to `main`.
2. In GitHub, open **Releases → Draft a new release**.
3. Create the tag `v1.0.0` on the commit containing those changes.
4. Click **Publish release**. Follow the build and publication in **Actions**.

The package version comes from `pyproject.toml`, not the tag or release title.
Use a matching tag and a new package version for each publication.

One-time setup: create the `pypi-release` GitHub environment and add a GitHub
Trusted Publisher in the PyPI project's Publishing settings with:

- Owner: `offerrall`
- Repository: `PyGrbl_Streamer`
- Workflow filename: `build.yml`
- Environment: `pypi-release`

Authentication uses OIDC (`id-token: write`); no PyPI API token secret is needed.
See [PyPI's Trusted Publisher setup](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).


The 1.x public API keeps existing calls compatible. Add controller-specific
behavior through optional arguments with existing defaults preserved. A
breaking public API change requires a new major version.
