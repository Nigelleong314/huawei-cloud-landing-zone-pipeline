"""lz_spec - the Landing Zone specification schema and its direct consumers.

schema.py is the single source of truth for the spec's sheets, tables, and
fields; gen_template renders the blank workbook from it, build_envs parses a
filled workbook back, and verify_pipeline is the regression harness that
keeps all of them honest.
"""
