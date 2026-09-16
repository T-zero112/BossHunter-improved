# Resume Template Source Inventory

This folder stores external open-source resume template sources for BossHunter template-center adaptation.

## Reactive Resume

- Repository: `https://github.com/reactive-resume/reactive-resume`
- Local path: `external/resume-template-sources/reactive-resume`
- License: MIT
- Template source path: `packages/pdf/src/templates`
- Preview JPG path: `apps/web/public/templates/jpg`
- Preview PDF path: `apps/web/public/templates/pdf`

Templates:

- `azurill`
- `bronzor`
- `chikorita`
- `ditgar`
- `ditto`
- `gengar`
- `glalie`
- `kakuna`
- `lapras`
- `leafish`
- `meowth`
- `onyx`
- `pikachu`
- `rhyhorn`
- `scizor`

## RenderCV

- Repository: `https://github.com/rendercv/rendercv`
- Local path: `external/resume-template-sources/rendercv`
- License: MIT
- Theme config path: `src/rendercv/schema/models/design/other_themes`
- Typst examples path: `src/rendercv/renderer/rendercv_typst/examples`
- Example preview images: `docs/assets/images/examples`
- Example PDFs/YAML files: `examples`

Themes:

- `classic`
- `ember`
- `engineeringclassic`
- `engineeringresumes`
- `harvard`
- `ink`
- `moderncv`
- `opal`
- `sb2nov`

## Adaptation Notes

- Treat these folders as upstream sources. Do not edit them directly when building BossHunter templates.
- Copy or translate selected templates into BossHunter's own template format.
- Keep MIT attribution in any derived template bundle.
- Prefer using existing preview images first, then implement matching HTML/CSS renderers inside BossHunter.
