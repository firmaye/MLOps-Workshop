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

## Chunking, PDF vs Markdown (2026-10-21)

Two ways to cut the text into passages, set by `--chunking` (rag.py):

- **fixed**: overlapping windows of 200 words (40 overlap) within one page, as the lesson does with the PDFs.
  On the Markdown, the same windows run over each page's Markdown text.
- **structure** (Markdown only): passages follow the headings, across page breaks. A section that fits in 200
  words is one passage; a longer one is cut at paragraph breaks; small sections are packed with the next. A table
  is never cut, and a table continued on the next page is first joined into one (27 joins: the F-75 and F-100
  annexes, glossaries, the TB adverse-event grading table, among others; a continuation whose header is
  reworded is left as a separate table). Each passage starts with its heading path
  ("4. CHOLERA OUTBREAK RESPONSE > 4.2. Case Management > Plan C: ..."), built from the printed section numbers
  because LlamaParse's heading levels are unreliable. Each passage has a page range (`page`..`end_page`, PDF page
  index); citations show it ("pages 28–29") and a retrieval hit counts if the expected page is in the range.
  417 of 1,187 passages span more than one page; mean 189 words, 19 over 400 (whole tables, up to 2,167 words
  for the F-75 annex: the embedding model reads only its first ~512 tokens).

**Retrieval only** (no LLM): right page among k=5 passages for the 22 answerable questions in
`eval_questions.csv`, and among k=8 for the 43 records with a page in `prescriptions.csv`. "Hit" counts the page
range; "first page" counts only a passage's first page (a strict lower bound for structure-based passages);
"pages read" is how many PDF pages the k passages cover on average (more pages = more text for the same k).

| Text | Chunking | Search | Passages | Eval hit | Eval, first page | Pages read | Check hit | Check, first page | Pages read |
|---|---|---|---|---|---|---|---|---|---|
| PDF | fixed | keyword | 2,163 | 17/22 | 17/22 | 5.0 | 35/43 | 35/43 | 8.0 |
| PDF | fixed | embedding | 2,163 | 16/22 | 16/22 | 5.0 | 41/43 | 41/43 | 8.0 |
| Markdown | fixed | keyword | 1,508 | 16/22 | 16/22 | 5.0 | 34/43 | 34/43 | 8.0 |
| Markdown | fixed | embedding | 1,508 | 18/22 | 18/22 | 5.0 | 40/43 | 40/43 | 8.0 |
| Markdown | structure | keyword | 1,187 | **20/22** | 16/22 | 6.9 | **41/43** | 38/43 | 10.3 |
| Markdown | structure | embedding | 1,187 | 16/22 | 13/22 | 7.0 | **41/43** | 39/43 | 10.6 |

The text alone (PDF vs Markdown, both fixed) moves retrieval by a question or two either way: noise at this
size. Structure-based chunks with keyword search find the right page most often, but part of that is the range
rule and the extra pages read (6.9 vs 5 per question); counted by first page only, they are no better. Embedding
search gains nothing from structure, plausibly because long passages are truncated before embedding.

**Prescription check v2** (default model `google/gemma-4-26b-a4b-it`, embeddings, k=8, judge `openai/gpt-oss-120b`),
one run each; per record in `results/check_v2_llm_reads_python_counts*.csv`:

| | PDF, fixed | Markdown, fixed | Markdown, structure |
|---|---|---|---|
| right page among the passages | 41/43 | 40/43 | 41/43 |
| errors caught | 12 of 22 | 15 of 22 | **17 of 22** |
| correct passed | 13 of 21 | 12 of 21 | **15 of 21** |
| false alarms | 2 of 21 | 3 of 21 | 3 of 21 |
| 'unsure' (sent to a person) | 13 of 44 | 7 of 44 | **6 of 44** |
| verdict = expected | 26 of 44 | 28 of 44 | **33 of 44** |
| empty verdict (reply not parseable) | 0 | 3 | 1 |
| faithfulness (Ragas judge, 44 scored) | 0.24 | 0.24 | 0.33 |

Most of the Markdown gain is the table-based records: on the PDF the LLM's quote from a flattened table (the
isoniazid weight bands, rx36–rx40) fails the grounding test and the verdict is "unsure"; quoted from a Markdown
table row it passes. Structure-based chunks add a few more right verdicts, as a dosing rule and its table now
arrive in one passage. One run per configuration, so a difference of one or two records is within the model's
run-to-run variation. Recurring on Markdown in both new runs: azithromycin's
"max 1 g" extracted as a maximum of 1 (mg), which Python flags as inconsistent ("unsure", rx07–rx09 with fixed
chunks, rx08–rx09 with structure); the Plan C quote copied across table cells, which fails the grounding test
(rx10, "unsure"); and replies holding two JSON objects (a self-correction), which leave `check.parse()` with no
verdict (rx42 in both; rx37 and rx39 too with fixed chunks).

An earlier Markdown loader (page-bounded, cut at headings; replaced by the two above) is kept in
`results/check_v2_llm_reads_python_counts_markdown.csv` for the record: 17/22 caught, 6/44 unsure; its judge scored
only 17 of 44 records (OpenRouter 402: the account had no credit loaded, and OpenRouter reserves the worst-case
cost of each in-flight request; the judge allows 8,192 output tokens, 4 at a time). Credit has since been added.
