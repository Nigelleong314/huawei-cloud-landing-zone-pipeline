# --- Identity module behaviour, provider-free ---
# Note: The mock provider never contacts Huawei Cloud; only planned values are checked.

mock_provider "huaweicloud" {}

variables {
  environment                 = "test"
  identity_store_id           = "store-0"
  identity_center_instance_id = "instance-0"
}

# --- Defaults equal what the live estates run today ---

run "baseline_defaults_unchanged" {
  command = plan

  module {
    source = "../../../terraform/modules/identity"
  }

  variables {
    enable_iam_baseline            = true
    enable_identity_center_content = false
  }

  assert {
    condition     = huaweicloud_identity_password_policy.this[0].password_validity_period == 90
    error_message = "Default password validity must stay 90 days."
  }
  assert {
    condition     = huaweicloud_identity_password_policy.this[0].password_char_combination == 2
    error_message = "Default character combination must stay 2."
  }
  assert {
    condition     = huaweicloud_identity_password_policy.this[0].number_of_recent_passwords_disallowed == 12
    error_message = "Default reuse prevention must stay 12."
  }
  assert {
    condition     = huaweicloud_identity_login_policy.this[0].session_timeout == 60
    error_message = "Default login session timeout must stay 60."
  }
  assert {
    condition     = huaweicloud_identity_protection_policy.this[0].protection_enabled == true
    error_message = "Operation protection must stay on by default."
  }
}

# --- A requested password policy actually reaches the resource ---

run "password_inputs_take_effect" {
  command = plan

  module {
    source = "../../../terraform/modules/identity"
  }

  variables {
    enable_iam_baseline            = true
    enable_identity_center_content = false
    iam_password_policy = {
      maximum_password_age      = 30
      password_char_combination = 3
    }
  }

  assert {
    condition     = huaweicloud_identity_password_policy.this[0].password_validity_period == 30
    error_message = "maximum_password_age = 30 must set a 30-day validity period."
  }
  assert {
    condition     = huaweicloud_identity_password_policy.this[0].password_char_combination == 3
    error_message = "password_char_combination = 3 must reach the resource."
  }
}

# --- Two groups may share a permission set in one account ---

run "shared_permission_set_provisions_once" {
  command = plan

  module {
    source = "../../../terraform/modules/identity"
  }

  variables {
    enable_iam_baseline            = false
    enable_identity_center_content = true
    groups = [
      { name = "ops" },
      { name = "sec" },
    ]
    permission_sets = {
      ReadOnly = { description = "Read only", system_policies = ["Tenant Guest"] }
    }
    account_assignments = [
      { account_id = "111", group_name = "ops", permission_set = "ReadOnly" },
      { account_id = "111", group_name = "sec", permission_set = "ReadOnly" },
      { account_id = "222", group_name = "ops", permission_set = "ReadOnly" },
    ]
  }

  assert {
    condition     = length(huaweicloud_identitycenter_account_assignment.this) == 3
    error_message = "Every group assignment must be kept."
  }
  assert {
    condition     = length(huaweicloud_identitycenter_provision_permission_set.this) == 2
    error_message = "Provisioning must be one per account and permission set."
  }
}

# --- The module-wide session duration is the fallback ---

run "session_duration_fallback" {
  command = plan

  module {
    source = "../../../terraform/modules/identity"
  }

  variables {
    enable_iam_baseline            = false
    enable_identity_center_content = true
    session_duration               = "PT4H"
    groups                         = []
    permission_sets = {
      Inherits = { description = "Uses the module default" }
      Explicit = { description = "Sets its own", session_duration = "PT2H" }
    }
  }

  assert {
    condition     = huaweicloud_identitycenter_permission_set.this["Inherits"].session_duration == "PT4H"
    error_message = "A permission set without its own duration must use session_duration."
  }
  assert {
    condition     = huaweicloud_identitycenter_permission_set.this["Explicit"].session_duration == "PT2H"
    error_message = "A permission set's own duration must win."
  }
}
