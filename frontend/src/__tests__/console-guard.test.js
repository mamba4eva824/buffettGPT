/**
 * Console Usage Guard Test
 *
 * Ensures production source code uses the logger utility instead of raw console.* calls.
 * Only logger.js itself is allowed to use console.* (it's the centralized logging layer).
 * Test files are excluded since they legitimately spy on console.
 */
import { describe, it, expect } from 'vitest';
import { execSync } from 'child_process';
import path from 'path';

const SRC_DIR = path.resolve(__dirname, '..');

describe('Console Usage Guard', () => {
  it('should not have raw console.log/error/warn in production source files (excluding logger.js and tests)', () => {
    // Use grep to find console.* usage in source files, excluding:
    // - logger.js (the centralized logger is allowed to use console)
    // - __tests__/ (test files legitimately spy on console)
    // - node_modules/
    let grepOutput = '';
    try {
      grepOutput = execSync(
        `grep -rn "console\\." "${SRC_DIR}" --include="*.js" --include="*.jsx" --include="*.ts" --include="*.tsx" | grep -v "__tests__" | grep -v "node_modules" | grep -v "logger.js" | grep -v "// eslint-disable"`,
        { encoding: 'utf-8', timeout: 10000 }
      ).trim();
    } catch (e) {
      // grep exits with code 1 when no matches found — that's the desired outcome
      if (e.status === 1) {
        grepOutput = '';
      } else {
        throw e;
      }
    }

    if (grepOutput) {
      const violations = grepOutput.split('\n').map(line => {
        // Make paths relative for readability
        return line.replace(SRC_DIR + '/', '');
      });

      // Fail with a descriptive message listing all violations
      expect(violations).toEqual([]);
    }

    // If we get here, no violations found
    expect(grepOutput).toBe('');
  });
});
