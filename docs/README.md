# Documentation Site

VitePress documentation for Hyperliquid Trading Agent.

## Setup

Install dependencies:
```bash
bun install
```

## Development

Run local dev server:
```bash
bun run docs:dev
```

Visit http://localhost:5173

## Build

Build static site:
```bash
bun run docs:build
```

Output will be in `.vitepress/dist/`

## Legacy Markdown

Historical reference documents are available under `legacy/`. They are preserved for convenience and can be ported into the VitePress content structure as needed.

## Deploy to GitHub Pages

1. Update `base` in `.vitepress/config.mts` to match your repo name
2. Build the site: `bun run docs:build`
3. Deploy the `.vitepress/dist` folder to GitHub Pages

### Automated Deployment

Add this GitHub Actions workflow at `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy Docs Site

on:
  push:
    branches:
      - main
    paths:
      - 'docs/**'
      - '.github/workflows/deploy-docs.yml'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: 'docs'
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Bun
        uses: oven-sh/setup-bun@v1
        with:
          bun-version: latest

      - name: Install dependencies
        working-directory: docs
        run: bun install

      - name: Build VitePress site
        working-directory: docs
        run: bun run docs:build

      - name: Upload GitHub Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs/.vitepress/dist

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```
