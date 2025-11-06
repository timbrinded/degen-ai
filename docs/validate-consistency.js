#!/usr/bin/env node

/**
 * Consistency Validator for VitePress Documentation
 * Checks terminology usage, formatting, and template compliance
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DOCS_ROOT = __dirname;
const DOCS_DIRS = ['guide', 'architecture', 'strategies', 'api'];

// Define standard terminology
const TERMINOLOGY = {
  'Trading Agent': ['trading agent', 'TradingAgent'],
  'Governed Agent': ['governed agent', 'GovernedAgent'],
  'Signal System': ['signal system', 'signals'],
  'Governance System': ['governance system', 'governance'],
  'Market Registry': ['market registry', 'MarketRegistry'],
  'Hyperliquid': ['Hyperliquid', 'hyperliquid'],
};

// Track issues
const issues = {
  terminology: [],
  formatting: [],
  template: [],
};

/**
 * Get all markdown files
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
 * Check terminology consistency
 */
function checkTerminology(content, filePath) {
  const relativePath = path.relative(DOCS_ROOT, filePath);
  
  // Check for inconsistent capitalization
  const lines = content.split('\n');
  lines.forEach((line, idx) => {
    // Skip code blocks
    if (line.trim().startsWith('```')) return;
    
    // Check for common inconsistencies
    if (line.match(/hyperliquid trading agent/i) && !line.match(/Hyperliquid Trading Agent/)) {
      issues.terminology.push({
        file: relativePath,
        line: idx + 1,
        issue: 'Inconsistent capitalization: should be "Hyperliquid Trading Agent"',
        text: line.trim().substring(0, 80)
      });
    }
  });
}

/**
 * Check formatting consistency
 */
function checkFormatting(content, filePath) {
  const relativePath = path.relative(DOCS_ROOT, filePath);
  const lines = content.split('\n');
  
  let inCodeBlock = false;
  let codeBlockLang = null;
  
  lines.forEach((line, idx) => {
    // Track code blocks
    if (line.trim().startsWith('```')) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        const match = line.match(/```(\w+)?/);
        codeBlockLang = match ? match[1] : null;
        
        // Check for language specification
        if (!codeBlockLang && line.trim() === '```') {
          issues.formatting.push({
            file: relativePath,
            line: idx + 1,
            issue: 'Code block missing language specification',
            text: line
          });
        }
      } else {
        inCodeBlock = false;
        codeBlockLang = null;
      }
      return;
    }
    
    // Skip checks inside code blocks
    if (inCodeBlock) return;
    
    // Check for proper heading spacing
    if (line.startsWith('#')) {
      // Check if previous line is empty (except for first line)
      if (idx > 0 && lines[idx - 1].trim() !== '') {
        issues.formatting.push({
          file: relativePath,
          line: idx + 1,
          issue: 'Heading should have blank line before it',
          text: line.substring(0, 80)
        });
      }
      
      // Check if next line is empty (except for last line)
      if (idx < lines.length - 1 && lines[idx + 1].trim() !== '' && !lines[idx + 1].startsWith('#')) {
        issues.formatting.push({
          file: relativePath,
          line: idx + 1,
          issue: 'Heading should have blank line after it',
          text: line.substring(0, 80)
        });
      }
    }
  });
}

/**
 * Check template compliance for strategies
 */
function checkStrategyTemplate(content, filePath) {
  const relativePath = path.relative(DOCS_ROOT, filePath);
  
  // Only check strategy files
  if (!relativePath.startsWith('strategies/') || relativePath === 'strategies/index.md') {
    return;
  }
  
  const requiredSections = [
    '## Overview',
    '## Entry Rules',
    '## Exit Rules',
    '## Risk Parameters',
    '## Regime Compatibility',
  ];
  
  requiredSections.forEach(section => {
    if (!content.includes(section)) {
      issues.template.push({
        file: relativePath,
        issue: `Missing required section: ${section}`,
        type: 'strategy'
      });
    }
  });
}

/**
 * Check template compliance for architecture docs
 */
function checkArchitectureTemplate(content, filePath) {
  const relativePath = path.relative(DOCS_ROOT, filePath);
  
  // Only check architecture files
  if (!relativePath.startsWith('architecture/') || relativePath === 'architecture/overview.md') {
    return;
  }
  
  const requiredSections = [
    '## Overview',
  ];
  
  requiredSections.forEach(section => {
    if (!content.includes(section)) {
      issues.template.push({
        file: relativePath,
        issue: `Missing required section: ${section}`,
        type: 'architecture'
      });
    }
  });
}

/**
 * Main validation function
 */
function validateConsistency() {
  console.log('🔍 Checking documentation consistency...\n');
  
  // Collect all markdown files
  const markdownFiles = [
    path.join(DOCS_ROOT, 'index.md'),
    ...DOCS_DIRS.flatMap(dir => getMarkdownFiles(path.join(DOCS_ROOT, dir)))
  ];
  
  console.log(`📄 Checking ${markdownFiles.length} markdown files\n`);
  
  // Run checks on each file
  for (const file of markdownFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    
    checkTerminology(content, file);
    checkFormatting(content, file);
    checkStrategyTemplate(content, file);
    checkArchitectureTemplate(content, file);
  }
  
  // Report results
  console.log('✅ Consistency Check Results\n');
  console.log(`Terminology issues: ${issues.terminology.length}`);
  console.log(`Formatting issues: ${issues.formatting.length}`);
  console.log(`Template compliance issues: ${issues.template.length}\n`);
  
  const totalIssues = issues.terminology.length + issues.formatting.length + issues.template.length;
  
  if (totalIssues > 0) {
    if (issues.terminology.length > 0) {
      console.log('📝 Terminology Issues:\n');
      issues.terminology.slice(0, 10).forEach((issue, idx) => {
        console.log(`${idx + 1}. ${issue.file}:${issue.line}`);
        console.log(`   ${issue.issue}`);
        console.log(`   "${issue.text}"`);
        console.log('');
      });
      if (issues.terminology.length > 10) {
        console.log(`   ... and ${issues.terminology.length - 10} more\n`);
      }
    }
    
    if (issues.formatting.length > 0) {
      console.log('🎨 Formatting Issues:\n');
      issues.formatting.slice(0, 10).forEach((issue, idx) => {
        console.log(`${idx + 1}. ${issue.file}:${issue.line}`);
        console.log(`   ${issue.issue}`);
        console.log('');
      });
      if (issues.formatting.length > 10) {
        console.log(`   ... and ${issues.formatting.length - 10} more\n`);
      }
    }
    
    if (issues.template.length > 0) {
      console.log('📋 Template Compliance Issues:\n');
      issues.template.forEach((issue, idx) => {
        console.log(`${idx + 1}. ${issue.file}`);
        console.log(`   ${issue.issue} (${issue.type})`);
        console.log('');
      });
    }
    
    console.log(`\n⚠️  Found ${totalIssues} consistency issues (non-critical)`);
    console.log('These are suggestions for improvement, not blocking errors.\n');
  } else {
    console.log('✅ All consistency checks passed!');
  }
}

// Run validation
validateConsistency();
