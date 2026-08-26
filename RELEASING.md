# Releasing

This project follows [Semantic Versioning](https://semver.org/) and [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/). Package versions come from
the `version` field in `pyproject.toml`. The release tag must match that
version, prefixed with `v` (for example, `v0.1.0`).

## One-time PyPI Setup

The publication workflow uses [PyPI trusted publishing][trusted-publishing].
It exchanges a short-lived GitHub Actions OIDC identity for permission to
publish, so no PyPI API token or GitHub secret is needed.

1. Set the `PACKAGE_IMPORT_NAME` repository variable to
   `chrome_agent_bridge`. The test workflow uses it for the isolated package
   import and coverage checks:

   ```sh
   gh variable set PACKAGE_IMPORT_NAME \
     --repo palewire/chrome-agent-bridge \
     --body chrome_agent_bridge
   ```

2. Create a protected GitHub environment named `pypi`. Require a reviewer for
   this environment if the repository's release policy calls for approval.
3. On PyPI, add a trusted publisher for:
   - owner: `palewire`
   - repository: `chrome-agent-bridge`
   - workflow: `.github/workflows/continuous-deployment.yaml`
   - environment: `pypi`

For a package that does not exist yet, use PyPI's pending publisher form first.
The first tagged workflow run creates the project and publishes the package.
Do not add a `PYPI_TOKEN` secret.

Homebrew packaging is intentionally deferred until the package has demonstrated
enough demand to justify a formula.

## Release Checklist

- [ ] Document public package behavior in the Sphinx source under `docs/`.
- [ ] Update the `version` field in `pyproject.toml`.
- [ ] Review `CHANGELOG.md` and move relevant `Unreleased` entries into a
      dated version section.
- [ ] Choose a major, minor, or patch version according to Semantic Versioning.
- [ ] Run `make verify`.
- [ ] Run `make package-check PACKAGE=chrome_agent_bridge`.
- [ ] Run `make coverage PACKAGE=chrome_agent_bridge`.
- [ ] Obtain explicit human approval for the version and release.
- [ ] Merge the approved release PR.
- [ ] Confirm the exact version tag points to the release PR's merge commit.
- [ ] With explicit human approval, push the matching `vX.Y.Z` tag:

  ```sh
  git tag --annotate vX.Y.Z --message "Release vX.Y.Z" <merge-commit>
  git push origin vX.Y.Z
  ```

- [ ] Confirm the release workflow's build and PyPI publication jobs succeeded.
- [ ] Confirm the expected package version is available on PyPI.
- [ ] Complete the post-merge GitHub Release follow-up below.
- [ ] Confirm the documentation workflow deployed the matching Sphinx site.

## Post-merge GitHub Release Follow-up

Do not create the GitHub Release until the release PR has merged, the exact
version tag exists, and the approved package publication has completed. The tag
must point to the expected merge commit. Creating a tag, publishing a package,
or creating a release still requires explicit human approval.

1. Record the release PR's merge commit and confirm the exact tag resolves to
   it:

   ```sh
   VERSION=vX.Y.Z
   EXPECTED_COMMIT=<release-pr-merge-commit>
   git fetch origin --tags
   test "$(git rev-parse "${VERSION}^{commit}")" = "$EXPECTED_COMMIT"
   ```

2. Prepare concise release notes from the matching version section in
   `CHANGELOG.md`. After the package publication succeeds and with explicit
   human approval, create the GitHub Release from the existing tag:

   ```sh
   gh release create "$VERSION" \
     --verify-tag \
     --title "$VERSION" \
     --notes-file /path/to/release-notes.md
   ```

   The GitHub UI may be used instead, but select the existing tag and publish
   the release rather than creating a draft or prerelease.

3. Verify that the public release uses the expected tag and commit:

   ```sh
   test "$(gh release view "$VERSION" --json tagName --jq .tagName)" = "$VERSION"
   test "$(gh release view "$VERSION" --json isDraft,isPrerelease \
     --jq '(.isDraft == false and .isPrerelease == false)')" = "true"
   test "$(git rev-parse "${VERSION}^{commit}")" = "$EXPECTED_COMMIT"
   ```

## Documentation Deployment

Package documentation lives in this repository under `docs/`. The
`.github/workflows/docs.yaml` workflow builds the Sphinx site on every push and
pull request.

Before publishing documentation, protect the `docs-production` environment and
configure an AWS OIDC role with `DOCS_AWS_ROLE_ARN` and `DOCS_AWS_REGION`. Then
set the `DOCS_DEPLOY_ENABLED` repository variable to `true`. Keep deployment in
the same workflow so the published site always comes from the reviewed Sphinx
source in this repository.

## Agent Boundaries

Agents may update release documentation and run the checklist's validation
commands. They must not create tags, GitHub releases, documentation
deployments, or package publications without explicit human approval.

[trusted-publishing]: https://docs.pypi.org/trusted-publishers/
