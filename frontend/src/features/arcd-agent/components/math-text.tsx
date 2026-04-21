
import React, { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

type Segment =
  | { type: "text"; value: string }
  | { type: "math-inline"; value: string }
  | { type: "math-block"; value: string };

function parseSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let rest = text;

  while (rest.length > 0) {
    let bestIdx = rest.length;
    let bestType: "block-bracket" | "inline-bracket" | "block-dollar" | "inline-dollar" | null = null;

    const blockBracket = rest.indexOf("\\[");
    const inlineBracket = rest.indexOf("\\(");
    const blockDollar = rest.indexOf("$$");
    const inlineDollar = findSingleDollar(rest);

    if (blockBracket >= 0 && blockBracket < bestIdx) { bestIdx = blockBracket; bestType = "block-bracket"; }
    if (inlineBracket >= 0 && inlineBracket < bestIdx) { bestIdx = inlineBracket; bestType = "inline-bracket"; }
    if (blockDollar >= 0 && blockDollar < bestIdx) { bestIdx = blockDollar; bestType = "block-dollar"; }
    if (inlineDollar >= 0 && inlineDollar < bestIdx) { bestIdx = inlineDollar; bestType = "inline-dollar"; }

    if (bestType === null) {
      segments.push({ type: "text", value: rest });
      break;
    }

    if (bestIdx > 0) {
      segments.push({ type: "text", value: rest.slice(0, bestIdx) });
    }

    let closer: string, isBlock: boolean, openerLen: number, closerLen: number;
    switch (bestType) {
      case "block-bracket": closer = "\\]"; isBlock = true; openerLen = 2; closerLen = 2; break;
      case "inline-bracket": closer = "\\)"; isBlock = false; openerLen = 2; closerLen = 2; break;
      case "block-dollar": closer = "$$"; isBlock = true; openerLen = 2; closerLen = 2; break;
      case "inline-dollar": closer = "$"; isBlock = false; openerLen = 1; closerLen = 1; break;
    }

    const afterOpener = rest.slice(bestIdx + openerLen);
    const closeIdx = isBlock && bestType === "block-dollar"
      ? afterOpener.indexOf(closer)
      : bestType === "inline-dollar"
        ? findSingleDollar(afterOpener)
        : afterOpener.indexOf(closer);

    if (closeIdx < 0) {
      segments.push({ type: "text", value: rest.slice(bestIdx) });
      break;
    }

    const latex = afterOpener.slice(0, closeIdx).trim();
    if (latex) {
      segments.push({ type: isBlock ? "math-block" : "math-inline", value: latex });
    }
    rest = afterOpener.slice(closeIdx + closerLen);
  }

  return segments;
}

function findSingleDollar(text: string): number {
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "$" && text[i + 1] !== "$" && (i === 0 || text[i - 1] !== "$" && text[i - 1] !== "\\")) {
      return i;
    }
  }
  return -1;
}

function renderKatex(latex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      trust: true,
    });
  } catch {
    return latex;
  }
}

interface MathTextProps {
  text: string | null | undefined;
  className?: string;
}

export function MathText({ text, className }: MathTextProps) {
  const html = useMemo(() => {
    const segments = parseSegments(text ?? "");
    return segments
      .map((seg) => {
        if (seg.type === "text") {
          return seg.value
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        }
        if (seg.type === "math-inline") {
          return renderKatex(seg.value, false);
        }
        return `<div class="my-2">${renderKatex(seg.value, true)}</div>`;
      })
      .join("");
  }, [text]);

  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

interface MarkdownMathProps {
  text: string;
  className?: string;
}

function renderInlineMarkdown(line: string, hasMath: boolean): React.ReactElement[] {
  const tokens: React.ReactElement[] = [];
  let rest = line;
  let key = 0;

  while (rest.length > 0) {
    // images: ![alt](url)
    const imgMatch = rest.match(/^!\[([^\]]*)\]\(([^)]+)\)/);
    if (imgMatch) {
      tokens.push(
        <img
          key={key++}
          src={imgMatch[2]}
          alt={imgMatch[1]}
          className="inline-block max-w-full rounded-lg my-1 max-h-64"
        />
      );
      rest = rest.slice(imgMatch[0].length);
      continue;
    }

    // links: [text](url)
    const linkMatch = rest.match(/^\[([^\]]+)\]\(([^)]+)\)/);
    if (linkMatch) {
      tokens.push(
        <a
          key={key++}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary underline underline-offset-2 hover:text-primary/80"
        >
          {linkMatch[1]}
        </a>
      );
      rest = rest.slice(linkMatch[0].length);
      continue;
    }

    // inline code: `code`
    const codeMatch = rest.match(/^`([^`]+)`/);
    if (codeMatch) {
      tokens.push(
        <code key={key++} className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">
          {codeMatch[1]}
        </code>
      );
      rest = rest.slice(codeMatch[0].length);
      continue;
    }

    // bold: **text**
    const boldMatch = rest.match(/^\*\*([^*]+)\*\*/);
    if (boldMatch) {
      const inner = boldMatch[1];
      tokens.push(
        <strong key={key++}>
          {hasMath ? <MathText text={inner} /> : inner}
        </strong>
      );
      rest = rest.slice(boldMatch[0].length);
      continue;
    }

    // italic: *text* (not **)
    const italicMatch = rest.match(/^\*([^*]+)\*/);
    if (italicMatch) {
      const inner = italicMatch[1];
      tokens.push(
        <em key={key++}>
          {hasMath ? <MathText text={inner} /> : inner}
        </em>
      );
      rest = rest.slice(italicMatch[0].length);
      continue;
    }

    // plain text until next special character
    const nextSpecial = rest.search(/\*|`|!|\[|\\|\$/);
    if (nextSpecial <= 0) {
      const chunk = nextSpecial < 0 ? rest : rest.slice(0, 1);
      tokens.push(
        hasMath ? <MathText key={key++} text={chunk} /> : <span key={key++}>{chunk}</span>
      );
      rest = nextSpecial < 0 ? "" : rest.slice(1);
    } else {
      const chunk = rest.slice(0, nextSpecial);
      tokens.push(
        hasMath ? <MathText key={key++} text={chunk} /> : <span key={key++}>{chunk}</span>
      );
      rest = rest.slice(nextSpecial);
    }
  }

  return tokens;
}

export function MarkdownMath({ text, className }: MarkdownMathProps) {
  const lines = text.split("\n");
  const elements: React.ReactElement[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      elements.push(<div key={i} className="h-1.5" />);
      i++;
      continue;
    }

    // code block: ```...```
    if (line.trim().startsWith("```")) {
      const lang = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      elements.push(
        <pre key={`code-${i}`} className="bg-muted/80 rounded-lg p-3 text-xs font-mono overflow-x-auto my-2 border">
          {lang && <div className="text-[10px] text-muted-foreground mb-1 uppercase">{lang}</div>}
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    // block math: $$ on its own line
    if (line.trim() === "$$") {
      const mathLines: string[] = [];
      i++;
      while (i < lines.length && lines[i].trim() !== "$$") {
        mathLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      const latex = mathLines.join("\n").trim();
      if (latex) {
        elements.push(
          <div
            key={`bmath-${i}`}
            className="my-2"
            dangerouslySetInnerHTML={{ __html: renderKatex(latex, true) }}
          />
        );
      }
      continue;
    }

    const hasMath = /\\\(|\\\[|\$/.test(line);

    // headers
    const h3Match = line.match(/^### (.+)/);
    if (h3Match) {
      elements.push(
        <h4 key={i} className="font-semibold text-sm mt-3 mb-1">
          {renderInlineMarkdown(h3Match[1], hasMath)}
        </h4>
      );
      i++;
      continue;
    }
    const h2Match = line.match(/^## (.+)/);
    if (h2Match) {
      elements.push(
        <h3 key={i} className="font-semibold text-base mt-3 mb-1">
          {renderInlineMarkdown(h2Match[1], hasMath)}
        </h3>
      );
      i++;
      continue;
    }
    const h1Match = line.match(/^# (.+)/);
    if (h1Match) {
      elements.push(
        <h2 key={i} className="font-bold text-lg mt-3 mb-1">
          {renderInlineMarkdown(h1Match[1], hasMath)}
        </h2>
      );
      i++;
      continue;
    }

    // numbered list: 1. item
    const numMatch = line.match(/^(\d+)\.\s+(.+)/);
    if (numMatch) {
      elements.push(
        <div key={i} className="flex gap-2 pl-1">
          <span className="text-muted-foreground min-w-[1.2em] text-right">{numMatch[1]}.</span>
          <span>{renderInlineMarkdown(numMatch[2], hasMath)}</span>
        </div>
      );
      i++;
      continue;
    }

    // bullet list: - item or * item
    if (line.match(/^[-*]\s+/)) {
      const content = line.replace(/^[-*]\s+/, "");
      elements.push(
        <div key={i} className="flex gap-2 pl-1">
          <span className="text-muted-foreground">•</span>
          <span>{renderInlineMarkdown(content, hasMath)}</span>
        </div>
      );
      i++;
      continue;
    }

    // regular paragraph
    elements.push(<p key={i}>{renderInlineMarkdown(line, hasMath)}</p>);
    i++;
  }

  return <div className={className ?? "space-y-1"}>{elements}</div>;
}
