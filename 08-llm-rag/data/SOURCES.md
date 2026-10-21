# Guideline sources and the Markdown versions

The assistant reads six Ethiopian public health guidelines. The PDFs are downloaded from their publishers by
`python scripts/download.py guidelines` (URLs and checksums in [`scripts/downloads.json`](../../scripts/downloads.json))
and are not stored in this repository. Their Markdown versions, in [`../guidelines_md/`](../guidelines_md/), are.

| File stem | Document | Pages | Source URL |
|---|---|---|---|
| `ephi_cholera_2022` | EPHI: National Guideline for Cholera Surveillance and Outbreak Response (2022) | 124 | https://ephi.gov.et/wp-content/uploads/2022/11/Guideline_for_Cholera_Surveillance_and_Outbreak_Response_Final_V2.pdf |
| `ephi_emergency_nutrition_2022` | EPHI: Emergency Nutrition Guideline (2022) | 92 | https://ephi.gov.et/wp-content/uploads/2022/03/EPHI-Emergency-Nutrition-GuidelineOR.pdf |
| `ephi_climate_sensitive_diseases_2022` | EPHI: Climate-Sensitive Diseases Surveillance Manual (2022) | 110 | https://ephi.gov.et/wp-content/uploads/2022/07/EPHI_cPHEM_EWISMD_Climate_Sensitive_Diseases_Surveillance_Manual_2022.pdf |
| `ephi_cebs_2021` | EPHI: Community and Event-Based Surveillance Implementation Manual (2021) | 50 | https://ephi.gov.et/wp-content/uploads/2022/07/EPHI_cPHEM_EWISMD_CEBS_Implementation_Manual_2021.pdf |
| `moh_acute_malnutrition_2019` | Ministry of Health: National Guideline for the Management of Acute Malnutrition (May 2019; copy hosted by the Global Nutrition Cluster) | 156 | https://stg.nutritioncluster.net/sites/nutritioncluster.com/files/2022-06/National%20Guideline%20for%20Management%20of%20Acute%20Malnutrition%20May%202019%20Version.pdf |
| `moh_tb_2017` | Ministry of Health: National Guidelines for TB, DR-TB and Leprosy, 6th edition (2017; copy hosted by WHO AFRO) | 217 | https://afro.who.int/sites/default/files/2019-04/Ethiopia-National%20guidelines%20for%20TB%2C%20DR-TB%20and%20Leprosy%20in%20Ethiopia%20-%20Sixth%20Edition.pdf |

## Licence

None of the six documents carries a licence or copyright statement (checked in the full text). They are public
guidance from the Ethiopian Public Health Institute and the Ministry of Health, published on the open web for
health workers. **The Markdown files are a full-text copy of them**, which goes further than linking to the PDFs:
confirm with EPHI / the Ministry, or keep the repository private, before publishing it. Each file names its source
document; the text is the publishers' and is reproduced unchanged apart from layout.

## How the Markdown was made

Parsed with **LlamaParse** (LlamaIndex Cloud, v2 parse API, Python SDK `llama-cloud` 2.19) on **2026-10-21**, once,
by [`../facilitator/parse_guidelines.py`](../facilitator/parse_guidelines.py). Exact request parameters and job ids:
[`../guidelines_md/parse_log.json`](../guidelines_md/parse_log.json).

- **Tier `agentic`, version `2026-10-16`** (pinned). 10 credits/page; 749 pages = 7,480 credits, plus 420 for the
  pilots. `agentic_plus` (45/page, ~33,700 credits) does not fit the free plan's 20,000 a month. On the 6 pilot
  pages both tiers gave identical dosing numbers; agentic_plus only joined the F-75 table's two header rows, which
  the script's post-processing now does.
- **Custom prompt**: exact table rows and numbers, one header row per table, flowcharts as nested lists, charts as
  tables of values, heading levels kept, nothing added.
- **Output**: Markdown tables (`output_tables_as_markdown`, `compact_markdown_tables`), tables not merged across
  pages (`merge_continued_tables: false`, so every table stays on its page), `inline_images`, OCR language `en`,
  `extract_printed_page_number`; `expand=["markdown", "metadata"]`.
- **Pages**: one block per PDF page, opened by `<!-- page N -->`, where N is the **PDF page index** (1-based, what
  rag.py cites). Where the printed page number differs it is kept: `<!-- page 42 (printed 29) -->`.
- **Headers, footers, page numbers**: LlamaParse returns them apart from the page body. Page numbers and running
  heads (lines on 3+ pages) are dropped; what is left is kept at the end of its page: footnotes (6 pages in the
  cholera guideline, 4 in emergency nutrition) and one chapter heading (CEBS p18) taken for a running head.
- **Post-processing** (the script's `clean()`): image links dropped; two-row table headers that came back as a data
  row joined into the header; highlight marks (`<mark>`, `~~`) around cross-references in the acute malnutrition
  PDF removed; over-escaped `\\\*` normalised.

## Quality checks (2026-10-21)

**Quotes** (`python facilitator/check_quotes.py`; per quote in `../facilitator/quote_check.csv`): 65 verbatim
quotes (44 distinct) from `eval_questions.csv` and `prescriptions.csv`.

| Text | whitespace normalised | + Markdown syntax removed | letters and digits only (check.py's test) |
|---|---|---|---|
| Markdown | 34 of 65 | 48 of 65 | **63 of 65** |
| PDF text (pypdf) | 65 of 65 | 65 of 65 | 65 of 65 |

The quotes were copied from the pypdf text, so the PDF side matches by construction. Every miss is the quote's
pypdf artefact, not an error in the Markdown: broken hyphenation ("individu- als", "diag- nosis", "consecu - tive"),
stray spaces ("immedi ately", "6–1 1 months", "mg/ kg", "10 -14%"), a bullet glyph (U+F0B7, cebs_03), and table
cells flattened in reading order. The only quote not found even as letters and digits (rx37, rx38) is the
isoniazid weight-band table as pypdf flattens it, column by column ("< 5 5.1-9.9 … >25 50 100 … 300"); the
Markdown has the same cells row by row (`|< 5|50|½ tablet|`). Those quotes should be re-copied from the Markdown if
the lesson switches to it.

**Tables checked by eye against the PDF**, cell by cell, all exact: cholera p29 (Plan C Ringer's lactate, age
bands), p38 (antibiotics, two-column page); acute malnutrition p41 (OTP routine medicines), p58 (vitamin A by age),
p87 (TSFP medicines), p120 (F-75 volumes, 32 weight bands × 5 columns); emergency nutrition p52 (vitamin A
prophylaxis); TB p56 (INH weight bands), p205 (Annex 6: 21 drugs × 5–6 weight bands). Flowcharts (acute
malnutrition p25, TB p42) come out with every box's text; the arrows are mostly right (the pilot of p25 had one
extra arrow, the full run did not).

**Known imperfections**: footnote letters run into the text ("Volume of F-75 per Feed (ml)a"); rows that span a
table (bedaquiline in Annex 6) sit in the first value column; a heading carries over to the next page when that page
has none of its own (acute malnutrition p25 is under "Hospital Level" from p24). The documents contain no Amharic
text: Amharic only enters through two questions in `eval_questions.csv`.

## Retrieval and the prescription check, PDF vs Markdown (2026-10-21)

Retrieval only, no LLM: `python evaluate.py --retrieval-only [--retriever embed] --docs pdf|markdown` (right page
among k=5 passages, 22 answerable questions) and `python evaluate_check.py --retrieval-only ...` (right page among
k=8, 43 records with a page).

| | eval, keywords | eval, embeddings | check, keywords | check, embeddings |
|---|---|---|---|---|
| PDF (2,163 passages) | 17 of 22 | 16 of 22 | 35 of 43 | 41 of 43 |
| Markdown, first loader (cut at every heading; 1,815 passages) | 14 of 22 | 15 of 22 | 34 of 43 | 39 of 43 |
| Markdown, rag.py now (small sections packed, flowcharts as plain lines; 1,464 passages) | 17 of 22 | 16 of 22 | 35 of 43 | 39 of 43 |

The first loader's many tiny passages (20–40 words) crowded keyword search. With them packed, Markdown ties PDF;
the questions it wins and loses differ, both ways, one or two at a time: noise at this size.

Prescription check v2 (default model `google/gemma-4-26b-a4b-it`, embeddings, k=8), one run each;
`results/check_v2_llm_reads_python_counts.csv` (PDF) and `results/check_v2_llm_reads_python_counts_markdown.csv`:

| | PDF | Markdown |
|---|---|---|
| errors caught | 12 of 22 | **17 of 22** |
| correct passed | 13 of 21 | 14 of 21 |
| false alarms | 2 of 21 | 3 of 21 |
| 'unsure' (sent to a person) | 13 of 44 | **6 of 44** |
| said 'not covered' on a covered record | 1 of 43 | 0 of 43 |
| verdict = expected | 26 of 44 | 32 of 44 |
| faithfulness (Ragas judge) | 0.24 (44 scored) | 0.22, **only 17 of 44 scored** |

What changed, record by record (19 of 44 verdicts differ): the isoniazid records rx36–rx40 were all "unsure" on
the PDF (the LLM's quote of the flattened weight-band table failed the grounding test); from a Markdown table row
the quote passes, and all five are now right. rx11, rx13, rx16 and rx25 are now caught; rx35 now passes. New
problems on Markdown: three false alarms from wrong extractions: rx10 "over 30 minutes" taken as `over_hours` 30,
rx17 the ORS rule for a different situation (every hour), rx22 amoxicillin's `n_doses` 1. rx07–rx09 extract
azithromycin "20 mg/kg (max 1 g)" as maximum 1, a g/mg slip that Python flags as inconsistent ("unsure"). rx34 and
rx42 now pass a wrong prescription (rx34: the rule came back with a maximum and no minimum, so no amount was
compared; rx42: the general 10 mg/kg rule instead of the under-five restriction). rx29's reply holds two JSON
objects (a self-correction), which `check.parse()` cannot read, so its verdict is empty. One run each, so part of
this is the model's run-to-run variation. The judge failed on 27 records with OpenRouter error 402: the account had
no credit loaded (the $0.19 spent so far was all its usage), and OpenRouter reserves the worst-case cost of each
in-flight request (the judge allows 8,192 output tokens, 4 at a time). Credit has since been added.
