"""Are the verbatim quotes in eval_questions.csv and prescriptions.csv findable in the guideline text?

    python facilitator/check_quotes.py            # Markdown (guidelines_md/) and, for comparison, the PDF text

Three levels, strictest first, each in the whole document and on the cited page(s):
  ws      whitespace normalised only
  plain   also Markdown syntax removed (table pipes, **bold**, <sup>, list bullets, heading marks), quotes and
          dashes unified
  flat    letters and digits only, after HTML tags (<br/>, <sup>) are removed: check.py's own test of a quote
          (grounded()); rag.py removes <br/> from Markdown passages
"""

import re
import sys
from pathlib import Path

import pandas as pd

LESSON = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LESSON))
import rag  # noqa: E402
from check import flat  # noqa: E402


def ws(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def plain(s):
    s = re.sub(r"</?[a-zA-Z][^>]*>", " ", str(s))               # <sup>, <br/> (not "< 5 kg")
    s = re.sub(r"(?m)^\s*(#+|[*+-]|\d+\.)\s+", " ", s)        # headings, bullets
    s = re.sub(r"\|[-: |]+\|", " ", s)                        # table separator rows
    s = s.replace("\\*", "*").replace("\\_", "_")                # Markdown escapes
    s = s.replace("|", " ").replace("**", "").replace("__", "")
    s = s.translate(str.maketrans({"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', " ": " "}))
    return ws(s)


def pages_md(folder=rag.DOCS_MD):
    """doc -> {page: text} from the Markdown page markers."""
    out = {}
    for f in sorted(Path(folder).glob("*.md")):
        parts = rag.PAGE_MARK.split(f.read_text())
        out[f.stem] = {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    return out


def pages_pdf():
    from pypdf import PdfReader

    out = {}
    for f in sorted(rag.DOCS.glob("*.pdf")):
        out[f.stem] = {i: page.extract_text() or "" for i, page in enumerate(PdfReader(f).pages, 1)}
    return out


def quotes():
    q = pd.read_csv(LESSON / "eval_questions.csv", dtype=str).fillna("")
    r = pd.read_csv(LESSON / "prescriptions.csv", dtype=str).fillna("")
    rows = [(f"eval:{x.id}", x.doc, x.pages, x.quote) for x in q.itertuples() if x.quote]
    rows += [(f"rx:{x.id}", x.doc, x.pages, x.quote) for x in r.itertuples() if x.quote]
    return pd.DataFrame(rows, columns=["id", "doc", "pages", "quote"])


def findable(table, pages):
    levels = {"ws": ws, "plain": plain, "flat": lambda s: flat(re.sub(r"</?[a-zA-Z][^>]*>", " ", str(s)))}
    rows = []
    for t in table.itertuples():
        doc = pages.get(t.doc, {})
        cited = [int(p) for p in t.pages.split(";") if p.strip()]
        row = {"id": t.id}
        for name, norm in levels.items():
            q = norm(t.quote)
            row[name] = q in norm(" ".join(doc.values()))
            row[f"{name}_on_page"] = any(q in norm(doc.get(p, "")) for p in cited)
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    table = quotes()
    unique = table.drop_duplicates(["doc", "quote"])
    print(f"{len(table)} quotes ({len(unique)} distinct)\n")
    results = {}
    for name, pages in [("markdown", pages_md()), ("pdf", pages_pdf())]:
        res = findable(table, pages)
        results[name] = res
        print(f"{name:9s}" + "  ".join(f"{c}: {res[c].sum()}/{len(res)} (on cited page {res[c + '_on_page'].sum()})"
                                       for c in ["ws", "plain", "flat"]))
    md = table.merge(results["markdown"], on="id")
    misses = md[~md.plain]
    print(f"\nNot found in the Markdown after removing Markdown syntax ({len(misses)}; 'flat' = found as letters+digits):")
    for m in misses.drop_duplicates(["doc", "quote"]).itertuples():
        same = table[(table.doc == m.doc) & (table.quote == m.quote)].id.tolist()
        print(f"- {', '.join(same)} [{m.doc} p{m.pages}] flat={'yes' if m.flat else 'no'}: {m.quote[:110]}")
    out = LESSON / "facilitator" / "quote_check.csv"
    md.merge(results["pdf"].add_prefix("pdf_").rename(columns={"pdf_id": "id"}), on="id").to_csv(out, index=False)
    print(f"\nper quote: {out.relative_to(LESSON)}")


if __name__ == "__main__":
    main()
