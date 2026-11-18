const SKIP = new Set([
  "a", "an", "and", "are", "by", "do", "does", "for", "from", "how", "in", "is",
  "of", "on", "the", "to", "toward", "towards", "via", "what", "when", "why", "with",
]);

function plain(text) {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

// Same shape as Google Scholar keys: first author's surname, year, first real word of the title.
function citeKey(paper) {
  const surname = plain(paper.authors[0]?.split(/\s+/).at(-1) ?? "anon");
  const word = paper.title
    .split(/[^\p{L}\p{N}]+/u)
    .map(plain)
    .find((w) => w.length > 2 && !SKIP.has(w));
  return `${surname}${paper.published.slice(0, 4)}${word ?? ""}`;
}

function escape(text) {
  return text.replace(/[&%#]/g, (c) => `\\${c}`);
}

export function toBibtex(papers) {
  const used = new Map();
  const entries = papers.map((paper) => {
    let key = citeKey(paper);
    const count = used.get(key) ?? 0;
    used.set(key, count + 1);
    if (count > 0) key += String.fromCharCode(97 + count);

    return [
      `@misc{${key},`,
      `  title = {{${escape(paper.title)}}},`,
      `  author = {${paper.authors.join(" and ")}},`,
      `  year = {${paper.published.slice(0, 4)}},`,
      `  eprint = {${paper.id}},`,
      `  archivePrefix = {arXiv},`,
      `  primaryClass = {${paper.categories[0]}},`,
      `  url = {https://arxiv.org/abs/${paper.id}}`,
      `}`,
    ].join("\n");
  });
  return `${entries.join("\n\n")}\n`;
}
