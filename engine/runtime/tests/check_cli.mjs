// node check_cli.mjs fixtures.json -> JSON list of check() results (used by the Python parity test).
import { readFileSync } from 'node:fs';
import { check } from '../src/world.js';
const fx = JSON.parse(readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(fx.map(f => check(f.world, f.known ? new Set(f.known) : null))));
