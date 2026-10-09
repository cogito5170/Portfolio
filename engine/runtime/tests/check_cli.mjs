// node check_cli.mjs fixtures.json [violations] -> JSON list of check() (or rules violations()) results, one per
// fixture (used by the Python parity tests).
import { readFileSync } from 'node:fs';
import { check } from '../src/world.js';
import { violations } from '../src/rules.js';
const fx = JSON.parse(readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(fx.map(f => process.argv[3] === 'violations' ? violations(f.world) : check(f.world, f.known ? new Set(f.known) : null))));
