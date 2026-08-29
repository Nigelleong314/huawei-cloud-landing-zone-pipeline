data "terraform_remote_state" "foundation" {
  backend = "s3"
  config = {
    bucket                      = var.foundation_state_bucket
    key                         = var.foundation_state_key
    region                      = var.home_region
    endpoints                   = { s3 = "https://obs.${var.home_region}.myhuaweicloud.com" }
    access_key                  = var.master_access_key
    secret_key                  = var.master_secret_key
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket                      = var.network_state_bucket
    key                         = var.network_state_key
    region                      = var.home_region
    endpoints                   = { s3 = "https://obs.${var.home_region}.myhuaweicloud.com" }
    access_key                  = var.master_access_key
    secret_key                  = var.master_secret_key
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
  }
}

# Resolve the hub firewall's protected objects (0=internet/north-south,
# 1=VPC/east-west) from its instance ID (05-network cfw_id).
data "huaweicloud_cfw_firewalls" "this" {
  provider       = huaweicloud.cfw
  fw_instance_id = local.network.cfw_id

  lifecycle {
    postcondition {
      condition     = length(try(self.records[0].protect_objects, [])) > 0
      error_message = "Hub CFW instance not found or has no protected objects (cfw_id from 05-network). Apply 05-network first and verify its cfw_id output."
    }
  }
}

# Enterprise project the firewall lives in - the advanced-IPS-rules data source
# and the reverse-shell rule assertions are EP-scoped (a firewall in a non-default
# EP returns no advanced IPS rules under the default project "0").
data "huaweicloud_enterprise_project" "cfw" {
  count    = var.enterprise_project_name != "" ? 1 : 0
  provider = huaweicloud.cfw
  name     = var.enterprise_project_name
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
  network    = data.terraform_remote_state.network.outputs

  protect_objects    = try(data.huaweicloud_cfw_firewalls.this.records[0].protect_objects, [])
  internet_object_id = try([for o in local.protect_objects : o.object_id if tostring(o.type) == "0"][0], "")
  vpc_object_id      = try([for o in local.protect_objects : o.object_id if tostring(o.type) == "1"][0], "")

  cfw_enterprise_project_id = var.enterprise_project_name != "" ? data.huaweicloud_enterprise_project.cfw[0].id : "0"
}

module "cfw" {
  source    = "../../modules/cfw"
  providers = { huaweicloud = huaweicloud.cfw }

  fw_instance_id     = local.network.cfw_id
  internet_object_id = local.internet_object_id
  vpc_object_id      = local.vpc_object_id

  enterprise_project_id        = local.cfw_enterprise_project_id
  enable_anti_virus            = var.enable_anti_virus
  enable_reverse_shell_defense = var.enable_reverse_shell_defense

  alarm_topic_name             = var.alarm_topic_name
  enable_attack_alarm          = var.enable_attack_alarm
  enable_traffic_alarm         = var.enable_traffic_alarm
  enable_eip_unprotected_alarm = var.enable_eip_unprotected_alarm
  enable_threat_intel_alarm    = var.enable_threat_intel_alarm

  address_groups    = var.address_groups
  domain_groups     = var.domain_groups
  service_groups    = var.service_groups
  acl_rules         = var.acl_rules
  black_white_lists = var.black_white_lists
}
