# Terraform operator policy

`lz_pipeline.tools.gen_operator_policy` generates a least-privilege IAM 5.0 identity policy for
whoever runs `plan` / `apply` day to day, so routine runs no longer need an administrator key.

```bash
py -m lz_pipeline.tools.gen_operator_policy --state-bucket <state-bucket> --out tf-operator-policy.json
py -m lz_pipeline.tools.gen_operator_policy --spec lz.spec.json --out tf-operator-policy.json   # Global.Settings.state_bucket_name
```

The tool refuses a document over the 6,144-character IAM 5.0 custom-policy limit (the generated
policy is about 2,100 characters).

## Assigning it

- Create an Identity Center permission set (for example `TF-Operator`) and paste the JSON as its
  custom policy. No system policies are needed. The same document also works as an IAM 5.0
  identity policy on an IAM user group, for a CI user.
- Set the session duration to **at least 8 hours**. A full plan or apply that includes the cloud
  firewall takes about 40 minutes, and a session that expires during an apply cannot write the
  new state back.
- Assign it **in the management account only**. Terraform enters member accounts through
  `OrganizationAccountAccessAgency`, so member accounts need no assignment.
- To manage the permission set from the spec, add a row to `03_Identity.AppPermissionSets`:
  `Name` (for example `TF-Operator`), `SessionDuration` `PT8H`, `Description`, and the generated
  JSON in `CustomPolicy` (attached verbatim). Leave `EnterpriseProjects` blank. Assignments
  stay outside Terraform.

## What it allows

| Statement | Covers |
|---|---|
| ReadForPlan | read/list on Organizations, Identity Center, EPS, TMS, RAM; IAM projects, the role catalogue, account security policies |
| OrganizationsChange | update/move accounts, create/update OUs, create/update/attach/enable SCPs and tag policies, enable trusted services, register delegated administrators, tags |
| PermissionSetsChange | create/update/provision permission sets and attach/detach their policies, tags |
| EnterpriseProjectsAndTags | create/update/enable enterprise projects, create/update predefined tags |
| EnterMemberAccounts | assume `OrganizationAccountAccessAgency` through STS (`sts:agencies:assume`) |
| EnterMemberAccountsIam3 | the same through the IAM 3.0 assume call (`iam:tokens:assume`), which the provider's cross-account modes use |
| StateBucket / StateObjects | list, read and write objects in the state bucket only |

Keep both assume statements. Without `EnterMemberAccountsIam3`, every env that enters a member
account fails with a 403 on `iam:assume`.

## What it deliberately excludes

Use an administrator permission set for these; plans never need them, and an apply that does
fails with a 403 on that resource only.

- Irreversible or one-off: creating or closing accounts, deleting or leaving the organization,
  enabling RAM sharing, registering Identity Center regions.
- Removing a guardrail or org object: deleting or detaching SCPs, deleting OUs, disabling trusted
  services, deregistering delegated administrators, deleting permission sets, predefined tags or
  enterprise projects.
- Weakening account security: IAM password, login and protection policies; Identity Center MFA
  settings.
- Self-escalation: Identity Center account assignments, users and groups; IAM users, access keys
  agency grants, and role grants on enterprise projects.

**Known limit:** `PermissionSetsChange` can attach a broader policy to a permission set the
operator holds. Such a change always appears in the reviewed plan, so review plans for
permission-set policy changes before approving.
