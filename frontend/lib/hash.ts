/** Stable short hex fingerprint for feedback provenance (not crypto auth). */
export function contentHashHex(text: string, length = 32): string {
  // FNV-1a 32-bit then expand with rolling mix for more bits without WebCrypto async.
  let h1 = 0x811c9dc5;
  let h2 = 0x811c9dc5 ^ 0x9e3779b9;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    h1 ^= c;
    h1 = Math.imul(h1, 0x01000193);
    h2 ^= c + (i % 7);
    h2 = Math.imul(h2, 0x01000193);
  }
  const a = (h1 >>> 0).toString(16).padStart(8, "0");
  const b = (h2 >>> 0).toString(16).padStart(8, "0");
  return (a + b).slice(0, Math.min(length, 16));
}
