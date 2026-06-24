schema_version = 1

[adapter]
workspace = "generic"
shared_core = ".praxis/core.toml"
description = "Generic Praxis adapter loader. Project-specific routing belongs in the workspace."

[paths]
project_index = "praxis.projects.toml"
praxis_outputs = ".praxis/out"
contracts = ".praxis/contracts"
extensions = ".praxis/extensions"

[path_policy]
optional_external = []

[project_kinds.docs]
verification = "manual-doc-review"
candidate_accelerator = "none"

rule_paths = []
skill_paths = []

[extension_policy]
load_installed_extensions = true
extension_manifest = "extension.toml"
