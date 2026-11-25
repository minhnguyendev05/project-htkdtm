/*
 * CSV export helper.
 * SPEC §10 requires guarding against CSV formula injection, so any cell that
 * starts with = + - @ or a control character is prefixed with an apostrophe
 * before quoting.
 */

const FORMULA_PREFIX = /^[=+\-@\t\r]/;

function toCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value);
  const guarded = FORMULA_PREFIX.test(text) ? `'${text}` : text;
  return `"${guarded.replace(/"/g, '""')}"`;
}

export function downloadCsv(
  filename: string,
  headers: string[],
  rows: (string | number | null | undefined)[][],
): void {
  const content = [headers, ...rows]
    .map((row) => row.map(toCell).join(','))
    .join('\r\n');
  // BOM so Excel opens Vietnamese text in the right encoding.
  const blob = new Blob(['\uFEFF', content], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
