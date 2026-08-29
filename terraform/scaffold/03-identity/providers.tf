# Default provider = master account (IC content) -> master tags. Cross-account
# aliases (one per M1 account, IAM baseline) are GENERATED into
# providers.generated.tf and carry var.default_tags (member tags).

provider "huaweicloud" {
  region     = var.home_region
  access_key = var.master_access_key
  secret_key = var.master_secret_key

  default_tags = var.master_default_tags
}
