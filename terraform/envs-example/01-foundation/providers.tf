# Provider config for the foundation env.
#
# Module 1 runs in the master account only — single provider, no aliases needed.
# Subsequent envs (03-identity, 04-perimeter, etc.) read module 1's outputs and
# configure additional provider aliases for cross-account access.

# Master account. NO default_tags here: the only taggable resource in this env
# is huaweicloud_organizations_account, and org accounts must stay UNTAGGED
# (default_tags would stamp the master tag set onto every created account).
# Master-account IC content keeps its tags via 03-identity's own provider.
provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key
}
