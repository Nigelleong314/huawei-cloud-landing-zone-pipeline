"""lz_pipeline - the deterministic Landing Zone pipeline package.

The spec IR (lz.spec.json) is the canonical, git-diffable config store, with a
structural validator and a build path that consumes the IR. Builders/emitters
live in lz_pipeline.core; lz_spec.build_envs is the legacy workbook-path
entry, guaranteeing byte-identical output between the workbook and IR paths.

lz_spec is an ordinary installed package here; no path injection.
"""
