schema_version = 1

[platform]
name = "praxis-platform"
primary_command = "task"
portable = true
purpose = "Shared Praxis control plane for context, evidence, verification and closeout."
config_root = ".praxis"
output_root = ".praxis/out"

[[stage]]
id = "intake"
label = "Intake"
commands = ["context.brief"]
portable = true

[[stage]]
id = "verification"
label = "Verification"
commands = ["project.verify"]
portable = true

[[stage]]
id = "closeout"
label = "Closeout"
commands = ["project.readiness"]
portable = true
