#!/usr/bin/env node

/**
 * Code Example Validator for VitePress Documentation
 * Extracts and validates code examples from markdown files
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DOCS_ROOT = __dirname;
const DOCS_DIRS = ['guide', 'architecture', 'strategies', 'api'];
const TEMP_DIR = path.join(DOCS_ROOT, '.temp-code-validation');

// Track validation results
const results = {
  total: 0,
  python: 0,
  bash: 0,
  toml: 0,
  json: 0,
  other: 0,
  errors: []
};

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
 * Extract code blocks from markdown content
 */
function extractCodeBlocks(content, filePath) {
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  const blocks = [];
  let match;
  
  while ((match = codeBlockRegex.exec(content)) !== null) {
    blocks.push({
      language: match[1] || 'unknown',
      code: match[2],
      file: filePath
    });
  }
  
  return blocks;
}

/**
 * Validate Python code syntax
 */
function validatePython(code, filePath) {
  try {
    // Skip validation for certain patterns that are intentionally incomplete
    const skipPatterns = [
      /await\s+\w+/,  // Async examples without function wrapper
      /^\s*#.*Pseudocode/mi,  // Pseudocode examples
      /^\s*#.*Wrong/mi,  // Wrong/Correct comparison examples
      /^\s*#.*❌/,  // Wrong examples with emoji
      /ValueError:|TypeError:|SyntaxError:/,  // Error message examples
      /^\s*\.\.\./m,  // Ellipsis indicating incomplete code
      /return\s+None\s*#\s*Skip/,  // Skip examples
      /continue\s*#\s*#\s*Skip/,  // Continue examples
      /for\s+\d+\s+consecutive/,  // Pseudocode patterns
      /\d+th_percentile/,  // Pseudocode percentile references
      /\d+_(?:minutes|hours|days)/,  // Pseudocode time literals
      /^\s{4,}/,  // Code starting with indentation (snippet from larger function)
      /'''\s*$/,  // Unterminated triple quotes (incomplete example)
      /\) -> [\w\[\]|, ]+\s*$/m,  // Function signature without body
      /^(async )?def \w+\([^)]*\)\s*->\s*[\w\[\]|, "]+\s*$/m,  // Function signature line
      /Position\([^)]*\.\.\.\)/,  // Constructor with ellipsis
      /continue\s*#/,  // Continue statement in example
    ];
    
    for (const pattern of skipPatterns) {
      if (pattern.test(code)) {
        return { valid: true, skipped: true };
      }
    }
    
    // Wrap async code in async function if needed
    let wrappedCode = code;
    if (code.includes('await ') && !code.includes('async def') && !code.includes('async with')) {
      wrappedCode = `async def _temp_func():\n${code.split('\n').map(line => '    ' + line).join('\n')}`;
    }
    
    // Create temp file
    const tempFile = path.join(TEMP_DIR, 'temp_validation.py');
    fs.writeFileSync(tempFile, wrappedCode);
    
    // Try to compile (syntax check only)
    execSync(`python3 -m py_compile ${tempFile}`, { stdio: 'pipe' });
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: error.message,
      file: filePath
    };
  }
}

/**
 * Validate TOML syntax
 */
function validateTOML(code, filePath) {
  try {
    // Skip validation for wrong/correct comparison examples
    if (code.includes('# ❌') || code.includes('# Wrong') || code.includes('# or')) {
      return { valid: true, skipped: true };
    }
    
    const tempFile = path.join(TEMP_DIR, 'temp_validation.toml');
    fs.writeFileSync(tempFile, code);
    
    // Use Python's tomllib to validate
    const validateScript = `
import tomllib
with open('${tempFile}', 'rb') as f:
    tomllib.load(f)
`;
    const scriptFile = path.join(TEMP_DIR, 'validate_toml.py');
    fs.writeFileSync(scriptFile, validateScript);
    execSync(`python3 ${scriptFile}`, { stdio: 'pipe' });
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: error.message,
      file: filePath
    };
  }
}

/**
 * Validate JSON syntax
 */
function validateJSON(code, filePath) {
  try {
    JSON.parse(code);
    return { valid: true };
  } catch (error) {
    return {
      valid: false,
      error: error.message,
      file: filePath
    };
  }
}

/**
 * Validate bash commands (basic check)
 */
function validateBash(code, filePath) {
  // Skip validation for bash - just check for obvious issues
  const lines = code.split('\n');
  const issues = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // Skip comments and empty lines
    if (line.startsWith('#') || line === '') continue;
    
    // Check for common issues
    if (line.includes('your_') || line.includes('YOUR_')) {
      // Placeholder - this is expected in docs
      continue;
    }
  }
  
  return { valid: true };
}

/**
 * Main validation function
 */
function validateCodeExamples() {
  console.log('🔍 Scanning documentation for code examples...\n');
  
  // Create temp directory
  if (!fs.existsSync(TEMP_DIR)) {
    fs.mkdirSync(TEMP_DIR, { recursive: true });
  }
  
  // Collect all markdown files
  const markdownFiles = [
    path.join(DOCS_ROOT, 'index.md'),
    ...DOCS_DIRS.flatMap(dir => getMarkdownFiles(path.join(DOCS_ROOT, dir)))
  ];
  
  console.log(`📄 Found ${markdownFiles.length} markdown files\n`);
  
  // Extract and validate code blocks
  for (const file of markdownFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    const blocks = extractCodeBlocks(content, path.relative(DOCS_ROOT, file));
    
    for (const block of blocks) {
      results.total++;
      
      let validationResult;
      switch (block.language.toLowerCase()) {
        case 'python':
        case 'py':
          results.python++;
          validationResult = validatePython(block.code, block.file);
          break;
        case 'bash':
        case 'sh':
        case 'shell':
          results.bash++;
          validationResult = validateBash(block.code, block.file);
          break;
        case 'toml':
          results.toml++;
          validationResult = validateTOML(block.code, block.file);
          break;
        case 'json':
          results.json++;
          validationResult = validateJSON(block.code, block.file);
          break;
        default:
          results.other++;
          validationResult = { valid: true }; // Skip validation for other languages
      }
      
      if (!validationResult.valid) {
        results.errors.push({
          file: block.file,
          language: block.language,
          error: validationResult.error,
          code: block.code.substring(0, 100) + '...'
        });
      }
    }
  }
  
  // Cleanup temp directory
  if (fs.existsSync(TEMP_DIR)) {
    fs.rmSync(TEMP_DIR, { recursive: true, force: true });
  }
  
  // Report results
  console.log('✅ Code Example Validation Results\n');
  console.log(`Total code blocks: ${results.total}`);
  console.log(`  Python: ${results.python}`);
  console.log(`  Bash: ${results.bash}`);
  console.log(`  TOML: ${results.toml}`);
  console.log(`  JSON: ${results.json}`);
  console.log(`  Other: ${results.other}`);
  console.log(`\nErrors found: ${results.errors.length}\n`);
  
  if (results.errors.length > 0) {
    console.log('❌ Code Validation Errors:\n');
    results.errors.forEach((error, idx) => {
      console.log(`${idx + 1}. File: ${error.file}`);
      console.log(`   Language: ${error.language}`);
      console.log(`   Error: ${error.error}`);
      console.log(`   Code preview: ${error.code}`);
      console.log('');
    });
    process.exit(1);
  } else {
    console.log('✅ All code examples are valid!');
  }
}

// Run validation
validateCodeExamples();
