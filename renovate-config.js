module.exports = {
  extends: ['github>OctopusDeploy/team-bmbb-renovate-config:default.json5'],

  // Produce conventional-commit PR titles so validate-pr-title passes
  semanticCommits: 'enabled',

  // pep621 covers pyproject.toml and updates uv.lock alongside it
  enabledManagers: ['pep621', 'github-actions'],

  packageRules: [
    {
      // The requires-python floor moves by hand with the CI matrix
      matchDepTypes: ['requires-python'],
      enabled: false,
    },
    {
      // Keep runtime ranges wide for consumers: in-range releases only update uv.lock, so CI tests against them
      matchDepTypes: ['project.dependencies'],
      rangeStrategy: 'update-lockfile',
    },
    {
      // Dev and build tooling has no consumers, so keep its floor in step with uv.lock
      matchDepTypes: ['dependency-groups', 'build-system.requires'],
      rangeStrategy: 'bump',
    },
    {
      // Lint, test and type-check tooling only; a green build is enough.
      // build-system.requires stays on manual review because it builds the published package.
      matchDepTypes: ['dependency-groups'],
      matchUpdateTypes: ['minor', 'patch'],
      automerge: true,
    },
    {
      // OpenFeature SDK updates are worth releasing as a minor version, even if not breaking
      matchPackageNames: ['openfeature-sdk'],
      matchUpdateTypes: ['minor', 'patch'],
      semanticCommitType: 'feat',
    },
    {
      // Consumers don't use uv.lock, so a lockfile-only update changes nothing they get. The rule above would
      // otherwise override the preset's chore type for these, and release an unchanged package.
      matchJsonata: ['isLockfileUpdate = true'],
      semanticCommitType: 'chore',
    },
  ],
};
