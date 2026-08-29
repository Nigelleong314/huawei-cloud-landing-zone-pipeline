# State surgery [REUSABLE]

Moving resources between states, splitting envs, and absorbing console
changes — without touching the cloud.

## Keys are contracts (both kinds)

- **State keys**: never rename a `backend.tf` key; a renamed env keeps its
  historical key forever, a genuinely new env gets a new key.
- **`for_each` keys**: renaming a spoke/subnet/rule whose resources are
  keyed by that name plans **destroy + recreate of the live resources**. A
  module-level `state mv` does NOT fix it — every per-key resource needs its
  own `state mv`, and replace cascades (e.g. an ER attachment replace) make
  dependent resources fail with update-forbidden errors
  ("attachment_id can't be updated"). Names used as keys are contracts;
  display names can change, keys cannot. If a rename is truly required,
  enumerate every keyed resource, `state mv` each, and expect to abort if a
  ForceNew cascade appears in the plan.

## Splitting an env (un-merge) — the recipe

1. **Backups first**: `terraform state pull` of the source env to two
   locations (scratch + the state-backup convention); tree copies of every
   file to be edited. Rollback = push the backup + restore files — nothing
   in the migration touches a cloud resource, so rollback is
   complete-by-construction.
2. Scaffold the new env with a **NEW state key**; its module call must keep
   the same module name and argument VALUES (inputs re-wired to
   `terraform_remote_state` reads must resolve to the same IDs at plan
   time) so moved addresses match.
3. `terraform init` the new env (creates its empty remote state).
4. Pull both states to local files;
   `terraform state mv -state=src.tfstate -state-out=dst.tfstate '<addr>' '<addr>'`
   per resource (data sources are not moved — they re-read on plan).
5. Push the destination state, then the edited source state.
6. **Gates**: plan in the new env → 0 add / 0 destroy (in-place cosmetics
   tolerable; ANY "must be replaced" = stop and roll back). Plan in the
   source env → moved module absent, 0 destroy.

## Absorbing console changes

- A console change (billing conversion, adopted route, email fix) is
  persisted with `terraform apply -refresh-only` — a plain `plan` refreshes
  in memory only and saves nothing.
- Always `terraform state pull` a backup before refresh-only or push.
- `terraform state push` bumps the serial itself — don't pre-increment.
- A resource created in the console first is adopted with `terraform import`
  (or absorbed by Optional+Computed refresh); record the console origin.
