terraform {
  backend "s3" {
    # key is the HISTORICAL (pre-renumber) env name - it pins the live OBS state; never change
    key                         = "envs/09-network-sgacl/terraform.tfstate"
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}
