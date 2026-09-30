# --- Test root for the identity module ---
# Note: Every run block in identity.tftest.hcl points at the module directly.

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    huaweicloud = { source = "huaweicloud/huaweicloud", version = "~> 1.87" }
  }
}
