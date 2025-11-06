#!/usr/bin/env node

/**
 * Link Validator for VitePress Documentation
 * Validates all internal markdown links in the docs-site
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DOCS_ROOT = __dirname;
const DOCS_DIRS = ['guide', 'architecture', 'strategies', 'api'];

// Track all markdown files and their links
const allFiles = new Set();
const brokenLinks = [];
const validLinks = [];

/**
 * Get all markdown files in a directory recursively
 */
function getMarkdownFiles(dir) {
  const files = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory() && entry.name !== 'node_modules' && entry.name !== '.vitepress') {
      files.push(...getMarkdownFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      files.push(fullPath);
    }
  }
  
  return files;
}

/**
 * Extract all markdown links from content
 */
function extractLinks(content) {
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  const links = [];
  let match;
  
  while ((match = linkRegex.exec(content)) !== null) {
    links.push({
      text: match[1],
      url: match[2],
      fullMatch: match[0]
    });
  }
  
  return links;
}

/**
 * Check if a link is internal (not external URL)
 */
function isInternalLink(url) {
  return !url.startsWith('http://') && 
         !url.startsWith('https://') && 
         !url.startsWith('mailto:') &&
         !url.startsWith('#');
}

/**
 * Resolve a link path relative to the source file
 */
function resolveLinkPath(sourceFile, linkUrl) {
  // Remove anchor if present
  const urlWithoutAnchor = linkUrl.split('#')[0];
  if (!urlWithoutAnchor) return null; // Just an anchor
  
  // Handle absolute paths from root
  if (urlWithoutAnchor.startsWith('/')) {
    let targetPath = path.join(DOCS_ROOT, urlWithoutAnchor);
    
    // If ends with /, try index.md
    if (urlWithoutAnchor.endsWith('/')) {
      return path.join(targetPath, 'index.md');
    }
    
    // If already has .md, use as-is
    if (urlWithoutAnchor.endsWith('.md')) {
      return targetPath;
    }
    
    // Try with .md extension
    return targetPath + '.md';
  }
  
  // Handle relative paths
  const sourceDir = path.dirname(sourceFile);
  let resolved = path.join(sourceDir, urlWithoutAnchor);
  
  // If ends with /, try index.md
  if (urlWithoutAnchor.endsWith('/')) {
    return path.join(resolved, 'index.md');
  }
  
  // Try with .md extension if not present
  if (!resolved.endsWith('.md')) {
    return resolved + '.md';
  }
  
  return resolved;
}

/**
 * Main validation function
 */
function validateLinks() {
  console.log('🔍 Scanning documentation files...\n');
  
  // Collect all markdown files
  const markdownFiles = [
    path.join(DOCS_ROOT, 'index.md'),
    ...DOCS_DIRS.flatMap(dir => getMarkdownFiles(path.join(DOCS_ROOT, dir)))
  ];
  
  markdownFiles.forEach(file => {
    const relativePath = path.relative(DOCS_ROOT, file);
    allFiles.add(relativePath);
  });
  
  console.log(`📄 Found ${allFiles.size} markdown files\n`);
  
  // Validate links in each file
  for (const file of markdownFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const links = extractLinks(content);
    const relativePath = path.relative(DOCS_ROOT, file);
    
    for (const link of links) {
      if (!isInternalLink(link.url)) {
        continue; // Skip external links
      }
      
      const resolvedPath = resolveLinkPath(file, link.url);
      if (!resolvedPath) {
        continue; // Just an anchor link
      }
      
      if (!fs.existsSync(resolvedPath)) {
        brokenLinks.push({
          file: relativePath,
          link: link.url,
          text: link.text,
          resolvedPath: path.relative(DOCS_ROOT, resolvedPath)
        });
      } else {
        validLinks.push({
          file: relativePath,
          link: link.url
        });
      }
    }
  }
  
  // Report results
  console.log('✅ Link Validation Results\n');
  console.log(`Total internal links checked: ${validLinks.length + brokenLinks.length}`);
  console.log(`Valid links: ${validLinks.length}`);
  console.log(`Broken links: ${brokenLinks.length}\n`);
  
  if (brokenLinks.length > 0) {
    console.log('❌ Broken Links Found:\n');
    brokenLinks.forEach(broken => {
      console.log(`  File: ${broken.file}`);
      console.log(`  Link: ${broken.link}`);
      console.log(`  Text: "${broken.text}"`);
      console.log(`  Expected: ${broken.resolvedPath}`);
      console.log('');
    });
    process.exit(1);
  } else {
    console.log('✅ All internal links are valid!');
  }
}

// Run validation
validateLinks();
