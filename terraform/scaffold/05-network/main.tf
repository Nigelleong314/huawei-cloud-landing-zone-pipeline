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

# Resolve the landing-zone enterprise project (in the hub account) by name.
# Blank name => default project ("0").
data "huaweicloud_enterprise_project" "lz" {
  count    = var.enterprise_project_name != "" ? 1 : 0
  provider = huaweicloud.hub
  name     = var.enterprise_project_name
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs

  enterprise_project_id = var.enterprise_project_name != "" ? data.huaweicloud_enterprise_project.lz[0].id : "0"

  # Default ram_share_principals: workloads OU (if the foundation state exposes it)
  # + all workload account IDs. try() tolerates a foundation applied before the
  # workloads_ou_id output existed (re-apply 01-foundation to populate it).
  default_ram_principals = concat(
    try([local.foundation.workloads_ou_id], []),
    [for k, v in local.foundation.accounts : v.id if v.role == "workload"],
  )

  # var.ram_share_principals entries may be account names (resolved to IDs via
  # the foundation accounts map), raw 32-hex account IDs, or OU IDs (ou-*) —
  # the latter two pass through unchanged.
  resolved_ram_principals = [
    for p in var.ram_share_principals :
    can(regex("^[0-9a-f]{32}$", p)) || startswith(p, "ou-")
    ? p
    : local.foundation.accounts[p].id
  ]
  effective_ram_principals = length(var.ram_share_principals) > 0 ? local.resolved_ram_principals : local.default_ram_principals
}

# ── Org-level RAM share enablement (master account) ─────────────────────────
# Enables organization sharing so spoke accounts auto-accept the ER share.
# Master-account operation, so it lives on the default provider here.
resource "huaweicloud_ram_organization" "share" {
  enabled = true
}

module "network_hub" {
  source = "../../modules/network"
  # owner = hub itself (the hub manages its own route tables). Required because the
  # module declares a huaweicloud.owner configuration_alias for spoke cross-account wiring.
  providers = {
    huaweicloud       = huaweicloud.hub
    huaweicloud.owner = huaweicloud.hub
  }

  # Org sharing must be enabled (master) before the in-module RAM share is created
  # so spoke accounts auto-accept the ER share.
  depends_on = [huaweicloud_ram_organization.share]

  environment           = var.environment
  enable_hub            = true
  enterprise_project_id = local.enterprise_project_id

  hub_vpcs                    = var.hub_vpcs
  inspection_cidr_reservation = var.inspection_cidr_reservation
  east_west_firewall_mode     = var.east_west_firewall_mode

  er_name                           = var.er_name
  er_asn                            = var.er_asn
  er_availability_zones             = var.er_availability_zones
  er_flow_log_name                  = var.er_flow_log_name
  er_share_name                     = var.er_share_name
  er_auto_accept_shared_attachments = var.er_auto_accept_shared_attachments

  er_attachments           = var.er_attachments
  er_route_tables          = var.er_route_tables
  inbound_route_table      = var.inbound_route_table
  outbound_route_table     = var.outbound_route_table
  snat_vpc_attachment      = var.snat_vpc_attachment
  cfw_default_route_tables = var.cfw_default_route_tables
  spoke_private_supernet   = var.spoke_private_supernet
  subnet_dns               = var.subnet_dns
  enable_vpc_flow_logs     = var.enable_vpc_flow_logs
  flow_log_retention_days  = var.flow_log_retention_days

  cfw_name = var.cfw_name

  cfw_flavor                  = var.cfw_flavor
  cfw_ips_protection_mode     = var.cfw_ips_protection_mode
  cfw_ips_patch_enabled       = var.cfw_ips_patch_enabled
  cfw_charging_mode           = var.cfw_charging_mode
  cfw_period_unit             = var.cfw_period_unit
  cfw_period                  = var.cfw_period
  cfw_auto_renew              = var.cfw_auto_renew
  cfw_acl_rules               = var.cfw_acl_rules
  cfw_address_groups          = var.cfw_address_groups
  cfw_service_groups          = var.cfw_service_groups
  cfw_lts_log_enable          = var.cfw_lts_log_enable
  cfw_lts_log_group_name      = var.cfw_lts_log_group_name
  cfw_lts_traffic_stream_name = var.cfw_lts_traffic_stream_name
  cfw_lts_access_stream_name  = var.cfw_lts_access_stream_name
  cfw_lts_attack_stream_name  = var.cfw_lts_attack_stream_name

  eips         = var.eips
  nat_gateways = var.nat_gateways
  snat_rules   = var.snat_rules
  dnat_rules   = var.dnat_rules

  elbs             = var.elbs
  elb_listeners    = var.elb_listeners
  elb_pools        = var.elb_pools
  elb_lts_group_id = ""

  ram_share_principals = local.effective_ram_principals
  # Hub account's domain id — owner half of the ER RAM-share URN.
  er_share_owner_account_id = try(local.foundation.accounts[var.hub_account].id, "")
}

# Spoke providers + per-VPC module calls are GENERATED (spokes.generated.tf /
# providers.generated.tf) from the SpokeVPCs table by build_envs.py.
