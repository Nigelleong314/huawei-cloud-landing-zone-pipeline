"""Minimal HCL template renderer (dependency-free).

Templates live in core/templates/*.tf.tmpl and use string.Template syntax:
${name} substitutes a variable; $$ renders a literal $ (needed if a template
ever contains Terraform's own ${} interpolation). Missing variables raise.

render_lines() returns the line list, matching the emitters'
compose-a-list-of-lines idiom so converted and unconverted emitters mix
freely while every byte stays golden-tested.
"""

import string
from pathlib import Path

TPL_DIR = Path(__file__).parent / "templates"


def render_lines(name: str, **vars) -> list:
    # splitlines() drops a trailing newline, matching the emitters' convention
    # of joining line lists with "\n".
    text = (TPL_DIR / name).read_text(encoding="utf-8")
    return string.Template(text).substitute(**vars).splitlines()
