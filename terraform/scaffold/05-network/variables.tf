variable "home_region" { type = string }
variable "master_access_key" {
  type      = string
  sensitive = true
}
variable "master_secret_key" {
  type      = string
  sensitive = true
}
variable "environment" {
  type    = string
  default = "shared"
}
variable "default_tags" {
  type    = map(string)
  default = {}
}

variable "foundation_state_bucket" { type = string }
variable "foundation_state_key" {
  type    = string
  default = "envs/01-foundation/terraform.tfstate"
}

variable "hub_account" {
  type        = string
  default     = "lz-infra"
  description = "Account name (must match M1) the hub network resources deploy into."
}

variable "enterprise_project_name" {
  type        = string
  default     = ""
  description = "Landing-zone enterprise project (in the hub account). Blank = default project."
}

variable "er_attachments" {
  type    = any
  default = []
}
variable "er_route_tables" {
  type    = any
  default = []
}

# Supernet covering all private CIDRs — the SNAT VPC auto-gets a <supernet> -> ER
# return route. Blank = no return route.
variable "spoke_private_supernet" {
  type    = string
  default = ""
}

# Auto-wiring: all hub + spoke VPC attachments associate to inbound_route_table
# (auto static route -> CFW) and propagate into outbound_route_table (CFW
# associated; auto static route -> snat_vpc_attachment).
variable "inbound_route_table" {
  type    = string
  default = "er-inbound"
}
variable "outbound_route_table" {
  type    = string
  default = "er-outbound"
}
variable "snat_vpc_attachment" {
  type    = string
  default = "vpc-dmz-att"
}

# Extra ER route tables that get an auto 0.0.0.0/0 -> CFW static route (dedicated
# hybrid tables for VPN/DC attachments — from ERRouteTables.DefaultToCFW).
variable "cfw_default_route_tables" {
  type    = list(string)
  default = []
}

# Hub-resolver DNS: DHCP DNS servers (max 2) on every hub + spoke subnet — the
# 08-network-dns inbound resolver endpoint IPs. Empty = Huawei default DNS.
variable "subnet_dns" {
  type    = list(string)
  default = []
}

# Per-VPC flow logs: every hub + spoke VPC gets its own '<vpc>-flowlog' LTS
# group/stream + a vpc_flow_log (all traffic). Aggregated via LogConverge rows.
variable "enable_vpc_flow_logs" {
  type    = bool
  default = false
}
variable "flow_log_retention_days" {
  type    = number
  default = 90
}

variable "cfw_lts_log_enable" {
  type    = bool
  default = true
}
variable "cfw_lts_log_group_name" {
  type    = string
  default = "lz-hub-cfw"
}
variable "cfw_lts_traffic_stream_name" {
  type    = string
  default = "cfw-traffic"
}
variable "cfw_lts_access_stream_name" {
  type    = string
  default = "cfw-access"
}
variable "cfw_lts_attack_stream_name" {
  type    = string
  default = "cfw-attack"
}

# ── Hub VPCs (REQUIRED — no defaults; see module 3 README for sizing) ──────

variable "hub_vpcs" {
  type = map(object({
    cidr = string
    subnets = list(object({
      name = string
      cidr = string
    }))
  }))
  description = "Hub VPCs (subnet AZ is not pinned — Huawei auto-places)."
}

variable "inspection_cidr_reservation" {
  type    = string
  default = "10.0.99.0/24"
}
variable "east_west_firewall_mode" {
  type    = string
  default = "er"
}

variable "er_name" {
  type    = string
  default = "lz-hub-er"
}
variable "er_flow_log_name" {
  type    = string
  default = "lz-hub-er-flow-log"
}
variable "er_share_name" {
  type    = string
  default = "lz-hub-er-share"
}
variable "er_auto_accept_shared_attachments" {
  type    = bool
  default = true
}
variable "cfw_name" {
  type    = string
  default = "lz-hub-cfw"
}

variable "er_asn" {
  type    = number
  default = 64512
}
variable "er_availability_zones" {
  type    = list(string)
  default = ["az1", "az5"]
}

variable "cfw_flavor" {
  type    = string
  default = "standard"
}
# IPS attack defense on the hub firewall. null = console-managed (not touched).
variable "cfw_ips_protection_mode" {
  type    = number
  default = null
}
variable "cfw_ips_patch_enabled" {
  type    = bool
  default = null
}
variable "cfw_charging_mode" {
  type    = string
  default = "postPaid"
}
variable "cfw_period_unit" {
  type    = string
  default = "month"
}
variable "cfw_period" {
  type    = number
  default = 1
}
variable "cfw_auto_renew" {
  type    = bool
  default = false
}
variable "cfw_acl_rules" {
  type    = any
  default = []
}
variable "cfw_address_groups" {
  type    = any
  default = []
}
variable "cfw_service_groups" {
  type    = any
  default = []
}

variable "eips" {
  type    = any
  default = []
}
variable "nat_gateways" {
  type    = any
  default = []
}

variable "snat_rules" {
  type    = any
  default = []
}
variable "dnat_rules" {
  type    = any
  default = []
}

variable "elbs" {
  type    = any
  default = []
}
variable "elb_listeners" {
  type    = any
  default = []
}
variable "elb_pools" {
  type    = any
  default = []
}

variable "ram_share_principals" {
  type    = list(string)
  default = []
}

# ── Spokes (deployed in the same apply) ────────────────────────────────────
variable "spokes" {
  type = map(object({
    account            = optional(string, "")
    vpc_name           = string
    vpc_cidr           = string
    er_attach          = optional(bool, true) # false = isolated spoke (no SpokeERAttachments row)
    er_attachment_name = optional(string, "")
    er_attach_subnet   = optional(string, "")
    auto_add_route     = optional(bool, false)
    vpc_tags           = optional(map(string), {})
    subnets = list(object({
      name = string
      cidr = string
      tags = optional(map(string), {})
    }))
  }))
  description = "Map keyed by spoke VPC NAME -> spoke VPC config (account + VPC + subnets + per-resource tags). The provider/module fan-out is generated from the SpokeVPCs table; the spoke default route (0.0.0.0/0 -> hub ER) is auto-wired."
}

# ── VPN (sheet 10_VPN, merged into 05-network) ────────────────────────────────