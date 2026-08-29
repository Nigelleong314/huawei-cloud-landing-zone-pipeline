output "internet_object_id" { value = local.internet_object_id }
output "vpc_object_id" { value = local.vpc_object_id }
output "address_group_ids" { value = module.cfw.address_group_ids }
output "domain_group_ids" { value = module.cfw.domain_group_ids }
output "service_group_ids" { value = module.cfw.service_group_ids }
output "acl_rule_ids" { value = module.cfw.acl_rule_ids }
output "black_white_list_ids" { value = module.cfw.black_white_list_ids }
