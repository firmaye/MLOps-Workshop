# Facilitator notes: TB chest X-ray screening (Wed 28 Oct, 09:30–12:30)

Facilitator: Yoni. Participants: EAII technical staff; most know classifiers well, fewer know DICOM or screening
programmes. The notebook does the work; your job is the PAUSEs and the decisions.

**The one sentence:** acquisition drift is loud if you check the right things; population shift is silent to
every input check, and only lab results reveal it.

## Timeline

| Clock | Block | Notebook part | Notes |
|---|---|---|---|
| 09:30–09:45 | Intro slides (setting, the decision, cost of each mistake, the Zambia study, the four steps) | – | 5–7 slides. Show the four-step table without results |
| 09:45–09:55 | Look at the data, including headers | 1 | Everyone runs the first cells; fix setup problems here |
| 09:55–10:15 | Step 1: build at Kanyama; the checks | 2 + checks | MLflow UI optional (`mlflow ui` in this folder) |
| 10:15–10:30 | Step 2: Chawama | 3 | PAUSE before the lab results |
| 10:30–10:45 | Break | | |
| 10:45–11:20 | Step 3: Chainda South, the bug, respond | 4 | The heart of the session; don't rush the bug |
| 11:20–11:45 | Step 4: HIV-positive at Kanyama | 5 | PAUSE before the lab results |
| 11:45–12:00 | Summary table; closing PAUSE | Summary | Ask two or three people for their answer |
| 12:00–12:30 | Discussion | | Questions below |

If 15 minutes behind at the break: run Evidently and the bootstrap cells without discussing them, and point to
exercises 3–5 as take-home.

## Per part: what to say, what to expect, what to ask

**Part 1 (look).** Expected: the clinic/header table; 6 sample images if the internet works (otherwise a one-line
message, fine). Say: "The header is free information. Most pipelines throw it away." PAUSE 1 answers to look for:
the Konica machine; the inverted pixel storage; "validate at each site before trusting it".

**Step 1.** Expected: ROC-AUC 0.80, sensitivity 0.84, specificity 0.52 on 155 held-out people (25 TB). Google's
model on the same group: ROC-AUC 0.90. Say: "A modest model, trained on about 360 X-rays. The question today is
not how good it is here, but what happens when it moves." The checks table: Kanyama's own 3% header mismatch is
11 images from a Rayence machine (real data).

**Step 2 (Chawama).** Expected checks: header 0%, feature drift 0.65, flag rate 0.41. PAUSE 2: good answers want
local lab results first; push on "how many?" Then: sensitivity 0.61 (41 TB cases). Say: "Same machine, quiet
checks, worse performance. The checks look at images; they can't see who walks through the door." Chawama's TB
prevalence is half of Kanyama's (8% vs 16%); milder disease is harder to see.

**Step 3 (Chainda South).** Expected: header 99%, feature drift 0.995, flag rate 0.00. PAUSE 3 is the best moment
of the session: "nobody flagged" sounds like good news to some people. Then 0 of 7 TB cases found. Evidently: 10 of
10 summaries drifted here, but also 6 at Chawama and 5 for HIV-positive: use it to say "drift means different,
not wrong; size matters". The bug: flag rate 0.36 (plausible), ROC-AUC 0.50. PAUSE 4: only the header check catches
it. Respond: the local threshold brings flags back (sensitivity 6 of 7) but ROC-AUC stays 0.65; Google's
multi-device model gets 0.83 at Chainda. PAUSE 5 answers: collect labelled local data, standardise acquisition,
use a model trained on many devices, and in every case validate locally. Decision: not promoted.

**Step 4 (HIV-positive at Kanyama).** Expected checks: header 3%, feature drift 0.59, flag rate 0.59 (all quiet).
PAUSE 6: they need per-group lab results; ask how many TB cases they'd want (we have 52). Then: our ROC-AUC 0.80 →
0.74 (intervals overlap); Google's 0.90 → 0.82, sensitivity 0.94 → 0.81 (intervals barely overlap). Smear-negative
TB 48% vs 38%. Say: "Nothing in the images warned us. This is the failure monitoring can't see."

**Summary.** Read the "which check caught what" table aloud. Closing PAUSE: take two or three answers; they feed
Friday's plans.

## Fallbacks

- **The notebook is committed executed**: if a laptop fails, participants read the outputs.
- **No internet:** sample images are skipped automatically. The Zambia table must be present: copy it from the USB
  stick to `downloads/zambia/GHAI_Final_Data_2023.csv` (or `python scripts/download.py zambia --from <USB>`).
- **Kaggle download fails in the room:** same USB copy.

## Discussion questions (30 min)

1. Which DICOM header fields would you check on every batch in your own imaging pipelines, and would a mismatch block or warn?
2. In routine screening, lab results exist mainly for flagged people. How would you estimate sensitivity in production? What would a random audit of non-flagged people cost?
3. A vendor offers a TB model "validated on 50,000 images". What would you ask before deploying it at a new clinic?
4. Should HIV-positive patients get a different threshold? Who decides, and what does it cost in lab tests?
5. Previous TB (exercise 1): old scars flag two in three previously treated people with Google's model. How would you design the programme around that?

## Facts you may be asked

- Data: Google + CIDRZ prospective study, three Lusaka clinics, 1,828 adults, all lab-tested (culture/Xpert);
  Kazemzadeh et al., *NEJM AI* 2024. Positive = bacteriologically confirmed; 207 clinically diagnosed count as negative.
- Features: torchxrayvision DenseNet-121 (trained on other public X-ray sets), via ONNX; 1024 numbers per image.
- The Kaggle column documented as "1 − TB Predictions" (`tb_predictions1`) is the TB score; it reproduces the
  study's decisions at 0.305 and 0.465.
- The images are © the original authors; the repo holds only features and header facts (see `data/SOURCES.md`).
