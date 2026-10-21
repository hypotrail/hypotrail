// Number formatting of the panel: a port of `mlkit.study.cite.fmt_number` (COMPANION-
// ADVANCED §9), so a number in the panel reads exactly as in the report. Python formats
// the exact binary value and rounds a tie to even; this port does the same from the
// exact decimal expansion that `toFixed` gives. test/test_format.py compares both on 200
// values in every format. The panel never computes a figure: it formats engine values.
//
// Frozen by WP-0. API: Hypotrail.format.number(value, fmt) and .FORMATS, .localTime(iso).
(function (HT) {
  'use strict';
  const FORMATS = ['int', 'pct0', 'pct1', 'pct2', 'f1', 'f2', 'f3', 'f4', 'auto'];

  function group(digits) {
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function increment(digits) {
    const out = digits.split('');
    let i = out.length - 1;
    while (i >= 0) {
      if (out[i] === '9') { out[i] = '0'; i -= 1; continue; }
      out[i] = String(Number(out[i]) + 1);
      return out.join('');
    }
    return `1${out.join('')}`;
  }

  /** [sign, integer digits, fraction digits] of |x| rounded to d decimals, ties to even. */
  function rounded(x, d) {
    const negative = x < 0 || Object.is(x, -0);
    const expansion = Math.abs(x).toFixed(Math.min(100, d + 30));
    const [whole, frac = ''] = expansion.split('.');
    const kept = whole + frac.slice(0, d);
    const rest = frac.slice(d);
    const first = rest.charAt(0);
    const tail = /[1-9]/.test(rest.slice(1));
    const odd = Number(kept.charAt(kept.length - 1)) % 2 === 1;
    const up = first > '5' || (first === '5' && (tail || odd));
    let digits = up ? increment(kept) : kept;
    if (digits.length < d + 1) digits = digits.padStart(d + 1, '0');
    return [negative, digits.slice(0, digits.length - d) || '0', digits.slice(digits.length - d)];
  }

  function fixed(x, d, { grouping = false } = {}) {
    if (Number.isNaN(x)) return 'nan';
    if (!Number.isFinite(x)) return x > 0 ? 'inf' : '-inf';
    if (Math.abs(x) >= 1e21) return String(x);
    const [negative, whole, frac] = rounded(x, d);
    const head = grouping ? group(whole.replace(/^0+(?=\d)/, '')) : whole.replace(/^0+(?=\d)/, '');
    return `${negative ? '-' : ''}${head}${d > 0 ? '.' + frac : ''}`;
  }

  function integer(x) {
    const [negative, whole] = rounded(x, 0);
    const digits = whole.replace(/^0+(?=\d)/, '');
    return `${negative && digits !== '0' ? '-' : ''}${group(digits)}`;
  }

  /** `cite.fmt_number(value, fmt)`; throws for an unknown format. */
  function number(value, fmt = 'auto') {
    if (!FORMATS.includes(fmt)) throw new Error(`unknown number format ${fmt}`);
    const x = Number(value);
    if (fmt === 'int') return integer(x);
    if (fmt.startsWith('pct')) return `${fixed(100 * x, Number(fmt.slice(3)))}%`;
    if (fmt.startsWith('f')) return fixed(x, Number(fmt.slice(1)));
    if (Number.isInteger(x)) return integer(x);
    if (Math.abs(x) >= 100) return fixed(x, 1, { grouping: true });
    if (Math.abs(x) >= 1) return fixed(x, 2);
    return fixed(x, 3);
  }

  /** A recorded ISO time in the viewer's local format (a clock of the view, not a figure). */
  function localTime(iso) {
    const t = Date.parse(iso);
    return Number.isNaN(t) ? String(iso || '') : new Date(t).toLocaleString();
  }

  HT.format = { number, FORMATS, localTime };
})(globalThis.Hypotrail = globalThis.Hypotrail || {});
