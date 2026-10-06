# Repository Guidelines

## Project Structure & Module Organization

The `photo-group-picker` workspace currently contains no application source, tests, assets, or dependency manifests. Its hidden directories are environment metadata; do not treat them as application modules or modify them for feature work.

When adding the initial implementation, organize files by responsibility and document the chosen layout in `README.md`. Suggested locations are `src/` for application code, `tests/` for automated tests, and `assets/` for non-sensitive sample media. These directories are recommendations, not existing project structure.

## Build, Test, and Development Commands

No build, test, or development commands are currently configured. When selecting a toolchain, provide reproducible installation, local startup, test, and production build commands in `README.md`. Commit the corresponding dependency manifest and lockfile. Do not document commands such as `npm test` until the repository actually supports them.

## Coding Style & Naming Conventions

Follow the conventions of the selected language and framework. Configure a formatter and linter before substantial implementation, and use their defaults consistently. Prefer descriptive module and function names, keep responsibilities focused, and avoid unrelated formatting changes. Establish indentation and filename conventions with the initial source files.

## Testing Guidelines

No testing framework or coverage threshold is established. Add tests alongside new behavior using the chosen framework's naming conventions. Prioritize observable behavior, edge cases, and regression cases for fixes. Use synthetic or anonymized photo fixtures, and document how to run the suite.

## Commit & Pull Request Guidelines

Git history is unavailable in this workspace, so existing commit conventions cannot be verified. Use concise, imperative subjects, such as `Add photo grouping controls`, and keep commits focused.

Pull requests should explain the change, link relevant issues, list validation performed, and include screenshots for visible interface changes. Explicitly identify checks that could not be run.

## Security & Configuration

Never commit credentials, private photos, or machine-specific paths. Keep secrets in local configuration excluded from version control, and provide placeholder configuration examples when needed.
