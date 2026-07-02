---
name: mom-tolaria-vault
description: '用于 IFC MOM docs Tolaria vault 的 note、type、relationship、wikilink、frontmatter 和 saved view 维护。适用于需求文档、知识库整理、类型建模和视图配置。'
user-invocable: true
---

# MOM Tolaria Vault

## 定位

`docs/` 是 Tolaria vault。通用需求目录、阶段文件和 ETL 资产仍由 `task req` / `task project` / `task etl` 生成；Tolaria 只负责知识组织、关系、类型和视图层。

需要了解 Tolaria 产品行为时，优先使用会话上下文提供的 Tolaria bundled agent docs；本 skill 只保存 IFC MOM vault 约定。

## Core Conventions

- Notes are Markdown files.
- Use the first H1 as the note title. Tolaria uses this title in the note list, wikilinks, search and display surfaces.
- Store note type in the `type:` frontmatter field.
- Use wikilinks in body text and frontmatter fields to connect notes.
- Prefer types and relationships for organization. Folder structure is optional and is not the primary source of meaning.
- Tolaria reads notes recursively from all folders and stores new notes in the vault root by default.
- Saved views live in `views/*.yml`.
- Files in `attachments/` are assets, not notes. Reference them from notes, but do not treat them as notes or types.
- Frontmatter properties that start with `_` are usually Tolaria-managed state. Leave them alone unless the user explicitly asks for them to change.

## Note Shape

```yaml
---
type: Note
related_to: "[[tolaria]]"
status: Active
url: https://example.com
---

# Example note

Body content in Markdown.
```

For generated Praxis requirement docs, keep the existing numbered directory structure and add Tolaria-compatible frontmatter and H1. Do not flatten a requirement directory into a single note.

## Types

Types are regular notes with `type: Type`. They define how notes of that type appear and which properties or relationships should be suggested for new notes.

```yaml
---
type: Type
_icon: rocket
_color: "#3b82f6"
_order: 0
_list_properties_display:
  - related_to
_sort: "property:onboarding:asc"
---

# Project
```

Empty properties and relationships in a type document become placeholders on new notes of that type. Values attached to properties in the type document become defaults for type instances.

Useful type metadata includes `icon`/`_icon`, `color`/`_color`, `order`/`_order`, `sidebar label`, `_list_properties_display`, `_sort`, `template`, `view` and `visible`. When editing an existing file, preserve the key style already used there instead of mass-normalizing underscored keys.

## Relationships

Any frontmatter property whose value contains `[[wikilinks]]` is treated as a relationship. Common relationship keys include `related_to`, `belongs_to` and `has`, but custom relationship names are valid too.

Preserve older relationship labels such as `Belongs to:` when editing existing notes that already use them.

Use quoted wikilinks for scalar frontmatter values and YAML lists for multi-value relationships.

## Wikilinks

- `[[filename]]` or `[[Note Title]]` for normal links.
- `[[filename|display text]]` for custom display text.
- Wikilinks work in frontmatter values and Markdown body.

## Saved Views

Saved views live in `views/*.yml`; Tolaria scans every `.yml` file in `views/`. The filename is the stable view id, so use kebab-case filenames such as `active-projects.yml`.

```yaml
name: Active Projects
icon: null
color: null
sort: "property:onboarding:asc"
filters:
  any:
    - field: type
      op: equals
      value: Project
    - field: related_to
      op: contains
      value: "[[tolaria]]"
```

View rules:

- `name` is required. `icon`, `color` and `sort` are optional.
- `sort` uses `option:direction`; built-ins include `modified`, `created`, `title` and `status`.
- Custom-property sorts use `property:<Property Name>`, for example `property:onboarding:asc`.
- `filters` must be a tree whose root is exactly one `all:` group or one `any:` group.
- Each filter condition uses `field`, `op` and usually `value`.
- `field` can target built-ins like `type`, `status`, `title`, `favorite` and `body`, plus frontmatter keys used in this vault.
- Supported operators: `equals`, `not_equals`, `contains`, `not_contains`, `any_of`, `none_of`, `is_empty`, `is_not_empty`, `before`, `after`.
- `any_of` and `none_of` expect `value` to be a YAML list.
- `regex: true` is supported with `equals`, `not_equals`, `contains` and `not_contains`.
- Relationship filters can use wikilinks in `value`, for example `"[[tolaria]]"`.
- Do not create JSON view files or `.view.json` filenames.

## Filenames

Use kebab-case for manually created vault notes, one note per file. Praxis-generated requirement files keep their existing numbered `序号-YYYY-MM-DD-HHmm-主题.md` convention.

## Agent Rules

- Create and edit notes using frontmatter and H1 conventions.
- Create and edit type documents when the user asks for note categories or defaults.
- Add or modify relationships without breaking existing wikilinks.
- Create and edit saved views in `views/`.
- Use `task docs -- tolaria-check [<需求名>|--all]` before broad Tolaria cleanup to get a metadata gap report without changing docs content.
- Use `task docs -- tolaria-publish <需求名>|--all` only when the user wants knowledge indexing, Type/view publication or relationship index publication; it must not replace `task req` / `task project` requirement structure.
- Update `AGENTS.md` only when the user asks for vault-level guidance changes.
- Use Portent as the default best-practice model when the user asks how to improve, organize or restructure the knowledge base. Combine Portent's types, relationships and capture -> organize -> archive lifecycle with Tolaria type documents, properties, Inbox, archive and saved views.

## Avoid

- Do not infer note type or meaning from folders.
- Do not treat files in `attachments/` as notes, types or view definitions.
- Do not silently overwrite an existing custom `AGENTS.md`.
- Do not rewrite installation-specific app configuration unless the user explicitly asks.
