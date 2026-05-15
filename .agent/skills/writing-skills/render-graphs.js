/**
 * Render graphviz diagrams from a skill's SKILL.md to SVG files.
 *
 * Usage:
 *   node render-graphs.js <skill-directory>           # Render each diagram separately
 *   node render-graphs.js <skill-directory> --combine # Combine all into one diagram
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function extractDotBlocks(markdown) {
  const blocks = [];
  const regex = /```dot\n([\s\S]*?)```/g;
  let match;
  while ((match = regex.exec(markdown)) !== null) {
    const content = match[1].trim();
    const nameMatch = content.match(/digraph\s+(\w+)/);
    const name = nameMatch ? nameMatch[1] : `graph_${blocks.length + 1}`;
    blocks.push({ name, content });
  }
  return blocks;
}

function renderToSvg(dotContent) {
  try {
    return execSync('dot -Tsvg', {
      input: dotContent,
      encoding: 'utf-8'
    });
  } catch (err) {
    console.error('Error running dot:', err.message);
    return null;
  }
}

function main() {
  const args = process.argv.slice(2);
  const skillDirArg = args.find(a => !a.startsWith('--'));
  if (!skillDirArg) {
    console.error('Usage: node render-graphs.js <skill-directory>');
    process.exit(1);
  }
  const skillDir = path.resolve(skillDirArg);
  const skillFile = path.join(skillDir, 'SKILL.md');
  const markdown = fs.readFileSync(skillFile, 'utf-8');
  const blocks = extractDotBlocks(markdown);
  const outputDir = path.join(skillDir, 'diagrams');
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir);
  for (const block of blocks) {
    const svg = renderToSvg(block.content);
    if (svg) {
      fs.writeFileSync(path.join(outputDir, `${block.name}.svg`), svg);
    }
  }
}
main();
