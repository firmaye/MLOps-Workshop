"""Facilitator step, run once: parse the six guideline PDFs into Markdown with LlamaParse.

Participants never run this. Its output, guidelines_md/<stem>.md, is committed; rag.py reads it with
`--docs markdown`. Re-run only if a PDF in scripts/downloads.json changes. Parsed on 2026-10-21 (exact
parameters and job ids: guidelines_md/parse_log.json; notes and quality checks: data/SOURCES.md).

    uv pip install "llama-cloud>=2.19"          # ad hoc, NOT in requirements.txt. The v2 SDK; llama-parse and
                                                # llama-cloud-services are its deprecated predecessors
    export LLAMA_CLOUD_API_KEY=...
    python facilitator/parse_guidelines.py --pilot             # 6 representative pages -> facilitator/pilot/agentic/
    python facilitator/parse_guidelines.py --pilot --tier agentic_plus     # the same pages, the dearer tier
    python facilitator/parse_guidelines.py                     # all six documents -> guidelines_md/ (~7,500 credits)
    python facilitator/parse_guidelines.py --only moh_tb_2017  # one document
    python facilitator/parse_guidelines.py --from-raw          # rebuild the Markdown from facilitator/raw/, no credits

Why these settings (LlamaParse v2 API; docs read on 2026-10-21 at developers.llamaindex.ai/llamaparse):
  - tier "agentic" (10 credits/page): the docs' recommendation for PDFs with tables, multi-column layouts and
    charts. "agentic_plus" (45/page; the docs' choice for the hardest tables and charts) would need ~33,700 credits
    for the 749 pages; this account's free plan has 20,000 a month and no pay-as-you-go. The pilot ran both tiers
    on the same 6 pages: every dosing number was identical; agentic_plus only joined the F-75 table's two header
    rows, which clean() now does.
  - version pinned to the dated release "latest" resolved to, so a re-run gives the same parser.
  - tables as Markdown tables, not merged across pages: a merged table would lose the page it is on, and we
    cite PDF pages. The custom prompt asks for exact rows and numbers, flowcharts as nested lists and charts as
    tables of values. Prompt aside, LlamaParse writes most flowcharts as Mermaid graphs (rag.py turns those into
    plain lines) and still returns some two-row table headers as a data row (clean() joins them).
  - one Markdown block per PDF page. LlamaParse returns each page's header and footer apart from its body; we drop
    from them the page numbers and the running heads/footers (lines repeated on 3+ pages) and keep the rest:
    footnotes (cholera, emergency nutrition) and one chapter heading taken for a running head. Each page starts
    with a marker `<!-- page N -->`, N the PDF page index (1-based, as rag.py cites); where the printed page number
    differs it is in the marker too: `<!-- page 42 (printed 29) -->`.
  - image links are dropped (the images are not kept; what a figure says is transcribed), and so are the acute
    malnutrition PDF's highlight marks around cross-references.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
LESSON = HERE.parent
REPO = LESSON.parent
PDFS = REPO / "downloads" / "guidelines"
OUT = LESSON / "guidelines_md"
PILOT_OUT = HERE / "pilot"
RAW = HERE / "raw"             # full API responses, headers and footers included (not committed)

TIER = "agentic"
VERSIONS = {"agentic": "2026-10-16", "agentic_plus": "2026-09-28"}   # what "latest" resolved to on the parse date
PROMPT = (
    "This is a national clinical and public health guideline. Reconstruct every table as a Markdown table, "
    "keeping every row, every column and every number exactly as printed (doses, mg/kg, weight bands, age bands, "
    "volumes, units). Give each table exactly ONE header row: when the printed table has two header rows or "
    "merged header cells, join them into each column's header (e.g. 'Volume per feed (ml): every 2 hours "
    "(12 feeds)'), never as a data row. Transcribe flowcharts, "
    "algorithms and decision diagrams as nested Markdown lists that follow the boxes and arrows, keeping every "
    "box's text and every branch condition (yes/no, cut-offs). Describe charts and graphs as a table of their "
    "values plus one sentence on what they show. Keep heading levels as in the document. Do not add anything "
    "that is not on the page."
)
PARAMS = {
    "tier": TIER,
    "version": VERSIONS[TIER],
    "agentic_options": {"custom_prompt": PROMPT},
    "processing_options": {"ocr_parameters": {"languages": ["en"]}},
    "output_options": {
        "markdown": {"tables": {"output_tables_as_markdown": True, "merge_continued_tables": False,
                                "compact_markdown_tables": True},
                     "inline_images": True},
        "extract_printed_page_number": True,
    },
}
EXPAND = ["markdown", "metadata"]

PILOT_PAGES = {                                    # the pages the pilot checks, and why
    "moh_acute_malnutrition_2019": "25,41,120",    # flow chart; amoxicillin and vitamin A table; F-75 feeding table
    "ephi_cholera_2022": "29",                     # Ringer's lactate rehydration table (age bands)
    "moh_tb_2017": "42,56",                        # diagnostic algorithm; isoniazid weight-band table
}


def parse(client, pdf, target_pages=None, params=PARAMS):
    kwargs = dict(params, upload_file=pdf, expand=EXPAND, timeout=3 * 3600)
    if target_pages:
        kwargs["page_ranges"] = {"target_pages": target_pages}
    t0 = time.time()
    result = client.parsing.parse(**kwargs)
    print(f"  {pdf.name}: {result.job.status}, {time.time() - t0:.0f} s, credits {result.job.usage and result.job.usage.credits}",
          flush=True)
    return result


def cells(row):
    row = row.strip()
    return [c.strip() for c in row[row.startswith("|"):len(row) - row.endswith("|")].split("|")]


def join_header_rows(table):
    """A printed table with two header rows can come back with the second one as the first data row:

        |Weight (kg)|Volume per feed (ml)|Volume per feed (ml)|Daily total|      <- merged cell, repeated
        |-|-|-|-|
        |Every 2 hours|Every 3 hours||||                                        <- second header row
    Join it into the header ("Volume per feed (ml): Every 2 hours"). Only when the repeated header cells and the
    filled cells of that row match one to one, and the row holds no number-only cell (so not a data row).
    """
    lines = table.splitlines()
    if len(lines) < 4:
        return table
    head, sub = cells(lines[0]), cells(lines[2])
    if len(head) != len(sub):
        return table
    repeated = [i for i in range(len(head)) if head[i] and ((i > 0 and head[i - 1] == head[i]) or
                                                          (i + 1 < len(head) and head[i + 1] == head[i]))]
    filled = [c for c in sub if c]
    if not repeated or len(filled) != len(repeated) or any(re.fullmatch(r"[\d.,\s–-]+", c) for c in filled):
        return table
    at = [i for i, c in enumerate(sub) if c]
    targets = repeated if at == repeated else (repeated if at == list(range(len(filled))) else None)
    if targets is None:
        return table
    for i, c in zip(targets, filled):
        head[i] = f"{head[i]}: {c}"
    return "\n".join(["|" + "|".join(head) + "|", lines[1]] + lines[3:])


def clean(markdown):
    """Drop image links (the image files are not kept; LlamaParse transcribes what is in a figure) and join
    second header rows into their table's header."""
    markdown = re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", markdown)
    # the acute malnutrition PDF's highlighted cross-references come back as <mark>~~see Table 6~~</mark>
    markdown = re.sub(r"</?(mark|u)>|~~", "", markdown)
    markdown = re.sub(r"\\{2,}\*", r"\\*", markdown)          # over-escaped footnote stars in table cells: \\\* -> \*
    markdown = re.sub(r"(?m)(?:^\|.*\|[ \t]*\n?)+", lambda m: join_header_rows(m.group(0).rstrip("\n")) + "\n", markdown)
    return markdown.strip()


def credits_left(client):
    """Remaining credits on the account (the job's own usage field comes back empty on the free plan)."""
    org = client.get("/api/v1/organizations", cast_to=object)[0]["id"]
    grants = client.get(f"/api/v1/organizations/{org}/usage", cast_to=object)["usage"]["active_free_credits_usage"]
    return sum(g["remaining_balance"] for g in grants)


def key(line):
    return re.sub(r"[^0-9a-z]", "", re.sub(r"<[^>]+>", "", line).lower())


def page_furniture(pages):
    """Running heads and footers: lines found in the header or footer of 3 or more pages."""
    seen = Counter(k for p in pages for part in (p.header, p.footer) for k in {key(x) for x in (part or "").splitlines()})
    return {k for k, n in seen.items() if n >= 3}


def kept_lines(part, furniture):
    """What LlamaParse put in a page's header or footer that is content, not furniture: footnotes (they land in
    the footer) and the odd heading taken for a running head. Page numbers and running titles are dropped."""
    lines = [x for x in (part or "").splitlines() if x.strip()]
    return "\n\n".join(x for x in lines if key(x) not in furniture
                        and not re.fullmatch(r"(page)?(\d+|[ivxlc]+)(page)?", key(x)))


def to_markdown(result, title):
    """One block per PDF page, each opened by a page marker; page numbers and running heads/footers left out."""
    printed = {p.page_number: p.printed_page_number for p in (result.metadata.pages if result.metadata else [])}
    pages = [p for p in result.markdown.pages if p.success]
    furniture = page_furniture(pages)
    blocks = [f"# {title}\n"]
    for page in result.markdown.pages:
        n = page.page_number
        shown = str(printed.get(n) or "")
        label = f" (printed {shown})" if re.fullmatch(r"\d+|[ivxlcIVXLC]+", shown) and shown != str(n) else ""
        if page.success:
            head, foot = kept_lines(page.header, furniture), kept_lines(page.footer, furniture)
            body = "\n\n".join(x for x in [f"## {head}" if head else "", clean(page.markdown), foot] if x)
        else:
            body = f"<!-- parse failed: {page.error} -->"
        blocks.append(f"<!-- page {n}{label} -->\n\n{body}\n")
    return "\n".join(blocks)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", action="store_true", help="only the PILOT_PAGES, into facilitator/pilot/")
    ap.add_argument("--tier", default=TIER, help="override the tier (the pilot compares agentic and agentic_plus)")
    ap.add_argument("--only", nargs="*", help="file stems to parse (default: all six)")
    ap.add_argument("--from-raw", action="store_true",
                    help="no parsing: rebuild the Markdown from the saved responses in facilitator/raw/ (no credits)")
    a = ap.parse_args()

    from llama_cloud import LlamaCloud
    from llama_cloud.types.parsing_get_response import ParsingGetResponse

    sys.path.insert(0, str(LESSON))
    import rag

    titles = rag.document_titles()
    stems = a.only or (list(PILOT_PAGES) if a.pilot else sorted(titles))
    out = PILOT_OUT / a.tier if a.pilot else OUT
    raw = out if a.pilot else RAW          # full responses, to rebuild the Markdown and see what went into headers/footers
    out.mkdir(parents=True, exist_ok=True)
    raw.mkdir(exist_ok=True)
    if a.from_raw:
        for stem in stems:
            result = ParsingGetResponse.model_validate_json((raw / f"{stem}.json").read_text())
            (out / f"{stem}.md").write_text(to_markdown(result, titles[stem]))
        return
    client, params = LlamaCloud(), dict(PARAMS, tier=a.tier, version=VERSIONS[a.tier])
    log_file = out / "parse_log.json"
    log = json.loads(log_file.read_text()) if log_file.exists() else {"documents": {}}
    for stem in stems:
        before = credits_left(client)
        result = parse(client, PDFS / f"{stem}.pdf", PILOT_PAGES.get(stem) if a.pilot else None, params)
        (out / f"{stem}.md").write_text(to_markdown(result, titles[stem]))
        (raw / f"{stem}.json").write_text(result.model_dump_json(indent=1))
        log["documents"][stem] = {"date": date.today().isoformat(), "pages": len(result.markdown.pages),
                                  "credits": before - credits_left(client), "job": result.job.id}
        log |= {"params": params, "expand": EXPAND}
        log_file.write_text(json.dumps(log, indent=1))
        print(f"    {log['documents'][stem]}", flush=True)


if __name__ == "__main__":
    main()
