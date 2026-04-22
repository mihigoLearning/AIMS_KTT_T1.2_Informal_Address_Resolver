# Process Log

**Candidate:** Munezero Mihigo Ribeus
**Challenge ID:** T1.2  
**Date:** 2026-04-22


## Tools Used

### Tool 1 — Claude
- **Purpose:** Scaffolding repo structure, writing initial resolver pipeline, debugging fuzzy matching failures
- **Sample prompts used:**

  *"The query 'ku muhanda ujya Remera hafi ya Airtel' returns None. The road prefix is contaminating the fuzzy match. Fix the matching pipeline to extract text after the modifier first."*
  *"Add iruhande rwa (Kinyarwanda for beside/next to) to the modifier map and write a unit test that verifies the coordinate offset is applied."*
- **Prompt discarded:** *"Use langid library for language detection."* — Discarded because langid adds a slow model load on first call, pushing latency above 100ms. Replaced with a fast word-set heuristic that runs in under 1ms.

---

## Hardest Decision

The hardest trade-off was choosing between `partial_ratio` and `token_set_ratio` as the primary fuzzy scorer, and at what cutoff to set the threshold. `partial_ratio` is better for descriptions where the landmark name appears as a substring of a longer phrase ("inyuma ya big pharmacy on RN3"), but it is too permissive and returns false positives on garbage input. `token_set_ratio` handles word-order variation and abbreviations better ("BK Arena" vs "Bank of Kigali Arena") but misses substring matches. I resolved this by running both scorers across multiple query variants — full text, post-modifier text, and road-prefix-stripped text — and taking the highest score. The cutoff of 65 was chosen by manual testing on 10 real-world inputs. A lower cutoff increased false positives; a higher one caused unnecessary escalations on valid but noisy inputs like "remaera airtel".
