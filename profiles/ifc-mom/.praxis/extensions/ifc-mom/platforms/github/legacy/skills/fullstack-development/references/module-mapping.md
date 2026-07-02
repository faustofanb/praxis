# 模块与目录映射

## 当前默认范围

- 当前主要业务模块：MES
- 当前优先分组：job
- 默认按单体启动方式开发与联调

## 后端 MES job 目录

- Mapper：`ifc-mom-column-max/lamp-mes/lamp-mes-biz/src/main/java/top/tangyh/lamp/mes/mapper/job`
- Manager：`ifc-mom-column-max/lamp-mes/lamp-mes-biz/src/main/java/top/tangyh/lamp/mes/manager/job`
- Service：`ifc-mom-column-max/lamp-mes/lamp-mes-biz/src/main/java/top/tangyh/lamp/mes/service/job`
- Controller：`ifc-mom-column-max/lamp-mes/lamp-mes-controller/src/main/java/top/tangyh/lamp/mes/controller/job`
- Entity：`ifc-mom-column-max/lamp-mes/lamp-mes-entity/src/main/java/top/tangyh/lamp/mes/entity/job`
- Query VO：`ifc-mom-column-max/lamp-mes/lamp-mes-entity/src/main/java/top/tangyh/lamp/mes/vo/query/job`
- Result VO：`ifc-mom-column-max/lamp-mes/lamp-mes-entity/src/main/java/top/tangyh/lamp/mes/vo/result/job`
- Save VO：`ifc-mom-column-max/lamp-mes/lamp-mes-entity/src/main/java/top/tangyh/lamp/mes/vo/save/job`
- Update VO：`ifc-mom-column-max/lamp-mes/lamp-mes-entity/src/main/java/top/tangyh/lamp/mes/vo/update/job`

## 前端 MES jobTime 目录

- API：`ifc-web-mom-max/apps/web-antd/src/api/mes/jobTime`
- 页面：`ifc-web-mom-max/apps/web-antd/src/views/mes/jobTime`

## 使用原则

1. 若当前需求仍在 MES job 分组内，默认优先落到以上目录。
2. 若需求进入 MES 其他分组，沿用同样的目录分组方式扩展。
3. 若代码生成结果目录与以上约定冲突，优先向现有目录结构收敛。
