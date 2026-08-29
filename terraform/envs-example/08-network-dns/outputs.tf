output "public_zone_ids" { value = module.dns.public_zone_ids }
output "private_zone_ids" { value = module.dns.private_zone_ids }
output "recordset_ids" { value = module.dns.recordset_ids }
output "resolver_endpoint_ids" { value = module.dns.resolver_endpoint_ids }
output "resolver_endpoint_ips" { value = module.dns.resolver_endpoint_ips }
output "resolver_rule_ids" { value = module.dns.resolver_rule_ids }
output "access_log_ids" { value = module.dns.access_log_ids }
