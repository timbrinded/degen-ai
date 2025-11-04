# Documentation Site

VitePress documentation for Hyperliquid Trading Agent.

## Setup

Install dependencies:
```bash
npm install
```

## Development

Run local dev server:
```bash
npm run docs:dev
```

Visit http://localhost:5173

## Build

Build static site:
```bash
npm run docs:build
```

Output will be in `.vitepress/dist/`

## Deploy to GitHub Pages

1. Update `base` in `.vitepress/config.mts` to match your repo name
2. Build the site: `npm run docs:build`
3. Deploy the `.vitepress/dist` folder to GitHub Pages

### Automated Deployment

Add this GitHub Actions workflow at `.github/workflows/deploy-docs.yml`:

```yaml
name: Deploy Docs

on:
  push:
    branches: [main]
    paths:
      - 'docs-site/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - name: Install dependencies
        run: cd docs-site && npm install
      - name: Build
        run: cd docs-site && npm run docs:build
      - name: Deploy
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: docs-site/.vitepress/dist
```
