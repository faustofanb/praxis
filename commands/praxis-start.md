---
description: 启动 Praxis Next formal requirement
---
<!-- Generated from commands/praxis-start.toml by adapters/render.mjs; do not edit. -->

使用中文根据用户参数启动 formal requirement 工作流。先执行 `praxis task formal-start --id <短ID> --title <中文标题> --json`，再执行 `praxis requirement create --id <需求ID> --task <任务ID> --title <中文标题> --json`。需要时提示后续 `transition` 与 `close`。在 requirement 建立前不要直接进入交付。
