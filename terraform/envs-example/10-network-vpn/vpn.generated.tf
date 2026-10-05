# --- Site-to-cloud VPN ---
# Note: Requires the VPC and ER outputs from 05-network.

module "vpn" {
  source    = "../../modules/vpn"
  providers = { huaweicloud = huaweicloud.vpn }

  enterprise_project_id = local.enterprise_project_id

  vpc_ids = merge(local.network.hub_vpc_ids, {
    "example-prod-a-vpc" = local.network.spoke_vpc_ids["example-prod-a-vpc"]
    "example-sbx-vpc"    = local.network.spoke_vpc_ids["example-sbx-vpc"]
  })
  subnet_ids         = local.network.hub_subnet_ids
  er_id              = local.network.er_id
  er_route_table_ids = local.network.route_table_ids

  gateways          = var.gateways
  customer_gateways = var.customer_gateways
  connections       = var.connections
}
