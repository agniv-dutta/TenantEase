/** Tiny markdown renderer for the model card. Supports headings, tables,
 *  blockquotes, bullet lists, bold and inline code — enough for our card. */

import type { ReactNode } from "react";

function inline(text: string, keyPrefix: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={`${keyPrefix}-b-${i}`}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<code key={`${keyPrefix}-c-${i}`}>{token.slice(1, -1)}</code>);
    }
    last = match.index + token.length;
    i += 1;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ source }: { source: string }) {
  const lines = source.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      blocks.push(<h3 key={key++} className="subhead">{inline(line.slice(4), `h3-${key}`)}</h3>);
      i += 1;
    } else if (line.startsWith("## ")) {
      blocks.push(<h2 key={key++} className="section-title">{inline(line.slice(3), `h2-${key}`)}</h2>);
      i += 1;
    } else if (line.startsWith("# ")) {
      blocks.push(<h1 key={key++} className="page-title">{inline(line.slice(2), `h1-${key}`)}</h1>);
      i += 1;
    } else if (line.startsWith("> ")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].startsWith("> ")) {
        quote.push(lines[i].slice(2));
        i += 1;
      }
      blocks.push(
        <blockquote key={key++} style={{ borderLeft: "3px solid var(--indigo-soft)", paddingLeft: "var(--s-3)", color: "var(--indigo-soft)" }}>
          {quote.map((q, qi) => (
            <p key={qi} style={{ margin: "0 0 var(--s-1)" }}>{inline(q, `q-${key}-${qi}`)}</p>
          ))}
        </blockquote>,
      );
    } else if (line.startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        rows.push(lines[i]);
        i += 1;
      }
      const parse = (r: string) => r.split("|").slice(1, -1).map((c) => c.trim());
      const header = parse(rows[0]);
      const body = rows.slice(2).map(parse);
      blocks.push(
        <table className="data" key={key++}>
          <thead>
            <tr>
              {header.map((h, hi) => (
                <th key={hi} scope="col">{inline(h, `th-${key}-${hi}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri}>
                {row.map((c, ci) => (
                  <td key={ci}>{inline(c, `td-${key}-${ri}-${ci}`)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      );
    } else if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i += 1;
      }
      blocks.push(
        <ul key={key++}>
          {items.map((it, ii) => (
            <li key={ii}>{inline(it, `li-${key}-${ii}`)}</li>
          ))}
        </ul>,
      );
    } else {
      blocks.push(<p key={key++}>{inline(line, `p-${key}`)}</p>);
      i += 1;
    }
  }

  return <div>{blocks}</div>;
}
