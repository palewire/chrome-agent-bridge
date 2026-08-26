# Project Setup

The template has been configured for `chrome-agent-bridge` v0.1.0.

Before the first release, a maintainer must:

1. Set the `PACKAGE_IMPORT_NAME` repository variable to `chrome_agent_bridge`.
2. Configure a PyPI trusted publisher for the `pypi` GitHub environment as
   described in [RELEASING.md](RELEASING.md).
3. Configure the production documentation URL and protected `docs-production`
   environment if documentation deployment is required.
4. Review [RELEASING.md](RELEASING.md), the project URLs in `pyproject.toml`,
   and the package publication settings.
