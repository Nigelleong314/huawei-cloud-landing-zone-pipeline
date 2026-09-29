"""An export must never carry working-copy metadata into a handover artifact.

An env tree kept under version control (envs-frasers is, since 2026-09-29)
has a .git directory beside the Terraform. copy_tree walks the tree, so
without an explicit exclusion the whole repository - internal commit
messages, and every earlier revision of files this exporter deliberately
filters - lands in the customer's zip. That happened once; this test is the
backstop.
"""

from pathlib import Path

from lz_pipeline import export_v2


def test_git_metadata_is_excluded():
    assert ".git" in export_v2.EXCLUDE_DIRS
    assert ".gitignore" in export_v2.EXCLUDE_NAMES
    assert ".gitattributes" in export_v2.EXCLUDE_NAMES


def test_copy_tree_skips_a_git_dir(tmp_path):
    src = tmp_path / "envs"
    (src / "01-foundation").mkdir(parents=True)
    (src / "01-foundation" / "main.tf").write_text(
        "# --- Foundation ---\n", encoding="utf-8")
    # a repository beside the Terraform, as a version-controlled env tree has
    git = src / ".git" / "objects" / "ab"
    git.mkdir(parents=True)
    (git / "cdef").write_bytes(b"binary object")
    (src / ".git" / "COMMIT_EDITMSG").write_text("internal note", encoding="utf-8")
    (src / ".gitignore").write_text("*.tfstate\n", encoding="utf-8")
    (src / ".gitattributes").write_text("* -text\n", encoding="utf-8")

    dst = tmp_path / "out"
    n = export_v2.copy_tree(src, dst, rewrite=True)

    assert n == 1, "only main.tf should have been copied"
    copied = {p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file()}
    assert copied == {"01-foundation/main.tf"}
    assert not (dst / ".git").exists()
