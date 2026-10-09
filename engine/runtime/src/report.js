// Self-test results to the headless harness (worldengine/headless.py): JSON -> UTF-8 -> base64 on the console.
// Long results go out in numbered parts (console line limits).
export function report(obj) {
  const bytes = new TextEncoder().encode(JSON.stringify(obj));
  let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const b64 = btoa(bin), part = 200000;
  if (b64.length <= part) console.log('WE_RESULT:' + b64);
  else for (let i = 0, n = Math.ceil(b64.length / part); i < n; i++) console.log(`WE_RESULT_PART:${i}/${n}:` + b64.slice(i * part, (i + 1) * part));
}
