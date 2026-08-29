output "er_id" { value = module.network_hub.er_id }
output "route_table_ids" { value = module.network_hub.route_table_ids }
output "hub_vpc_ids" { value = module.network_hub.hub_vpc_ids }
output "hub_subnet_ids" { value = module.network_hub.hub_subnet_ids }
output "inspection_cidr_reservation" { value = module.network_hub.inspection_cidr_reservation }
output "nat_gateway_ids" { value = module.network_hub.nat_gateway_ids }
output "eip_ids" { value = module.network_hub.eip_ids }
output "eip_addresses" { value = module.network_hub.eip_addresses }
output "cfw_id" { value = module.network_hub.cfw_id }
output "ingress_elb_ids" { value = module.network_hub.ingress_elb_ids }
output "ingress_elb_private_ips" { value = module.network_hub.ingress_elb_private_ips }
output "ram_share_id" { value = module.network_hub.ram_share_id }

# spoke_vpc_ids is GENERATED (outputs.generated.tf) from the SpokeVPCs table.
