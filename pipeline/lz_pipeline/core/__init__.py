"""lz_pipeline.core - the pipeline engine, split from lz_spec/build_envs.py.

Modules: parsing (workbook -> spec), validation, builders (spec -> tfvars),
emitters (spec -> generated HCL fan-outs), writer (env output), cli
(orchestration). lz_spec/build_envs.py remains as a compatibility shim
re-exporting this package's API.
"""
