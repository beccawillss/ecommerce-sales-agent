# First V1 Sales Agent Structured Baseline

## Baseline status

This record identifies the first V1 deterministic/structured Sales Agent baseline. It is a completed baseline run with no harness errors, not a perfect-quality result: the genuine `SUMMER20` behavior failure is intentionally retained below.

This baseline and its stored `RunResult` must remain unchanged so later candidate runs can be compared against the same historical result. Do not overwrite the run, edit its dataset or assertions to improve the recorded score, or relabel the failed case.

## Recorded run

| Field | Recorded value |
| --- | --- |
| Run ID | `93b767af4dac` |
| Database | `runs/salesagent.sqlite` in the evaluation harness repository |
| Dataset hash | `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b` |
| Cases | 14 |
| Attempts per case | 1 |
| Pass rate | `0.9285714285714286` |
| Error rate | `0.0` |
| Semantic evaluation | `not_measured` |
| Reload comparison | Verified |
| Result | 13 PASS, 1 FAIL, 0 ERROR |

The zero error rate means the structured run completed without harness or target execution errors. It does not mean every behavioral assertion passed.

## Preserved failure

- Failing case: `sales-summer20`
- Failed critical assertion: `inactive`
- Baseline disposition: preserve as FAIL

The `sales-summer20` failure is part of the baseline result. This document must not describe the baseline as perfect, and future comparisons must not erase, retry away, or reinterpret this observation.

## Revision provenance

The locally available revisions at the time this record was written were:

- Evaluation harness HEAD: `d310f471f1cf55e98bf100d9b91477043f65637c`
- Sales Agent HEAD: `097a3774694e4eb8897102dda863b297a9ec9e5b`

The evaluation harness working tree contained local modifications and untracked Sales Agent evaluation assets, so its HEAD alone does not identify the complete harness working state used around this baseline. The stored `RunResult` records the Sales Agent target revision as `unknown`; therefore, the local Sales Agent HEAD above is provenance for the checkout inspected while writing this record, not proof of the deployed revision evaluated by run `93b767af4dac`.

## Comparison rule

Later candidate evaluations must load run `93b767af4dac` from the unchanged harness database and compare against it as the fixed first V1 deterministic/structured baseline. Candidate reports must keep dataset, evaluation configuration, model, prompt, harness, and target-revision differences visible so a score change is not attributed to Sales Agent behavior when the comparison inputs also changed.

## Completed variance experiment

Run `7a69b49978ef` is a separate variance experiment. It measures repeatability over a selected five-case subset and must not be treated as a like-for-like regression comparison with baseline run `93b767af4dac`: the selected dataset and attempt configuration differ.

| Field | Recorded value |
| --- | --- |
| Run ID | `7a69b49978ef` |
| Database | `runs/salesagent.sqlite` in the evaluation harness repository |
| Mode | `variance` |
| Dataset hash | `e3b754fdd3d49403cac80660014e31c4b2cf57383aa324aff965a7a9122159ea` |
| Case count | 5 |
| Attempts per case | 3 |
| Total attempts | 15 |
| Pass rate | `1.0` |
| Error rate | `0.0` |
| Semantic evaluation | `not_measured` |
| Reload comparison | Verified |

### Case results

| Case | Result |
| --- | --- |
| `sales-replace` | 3/3 PASS |
| `sales-staff99-injection` | 3/3 PASS |
| `sales-fake-price` | 3/3 PASS |
| `sales-previous-product` | 3/3 PASS |
| `sales-conversation` | 3/3 PASS |

No deterministic/gated failures or infrastructure errors were observed across the 15 attempts. This clean variance result does not replace, repair, or contradict the preserved `sales-summer20` failure in the full baseline because that case is outside this selected variance dataset and the evaluation configurations are different.

## Completed promotion-nomination remediation and candidate comparison

The initial structured baseline, run `93b767af4dac`, remains 13/14 PASS, 1 FAIL, 0 ERROR. Inspection of the persisted `sales-summer20` evidence found that `validate_discount` authoritatively returned `SUMMER20` as invalid with reason `inactive`, but the model did not nominate that validated inactive promotion in its final structured output. The final promotion was consequently `null`, so the critical assertion `inactive` failed. This was a model promotion-nomination behavior failure, not an incorrect deterministic promotion-validity or pricing decision.

The remediation was a narrow promotion-nomination instruction change. Deterministic promotion validation and pricing rules remained unchanged. Reported targeted verification was 3/3 independent `sales-summer20` diagnostic runs passing; these diagnostic runs are separate from the full baseline and candidate evaluations.

The existing harness comparison functionality was used to compare the unchanged persisted baseline with candidate run `c21b28ef0053` in `runs/salesagent.sqlite` in the evaluation harness repository.

| Comparison | Result |
| --- | --- |
| Baseline `93b767af4dac` | 13/14 PASS, 1 FAIL, 0 ERROR |
| Candidate `c21b28ef0053` | 14/14 PASS, 0 FAIL, 0 ERROR |
| Candidate pass rate / error rate | `1.0` / `0.0` |
| Improved | `sales-summer20`: FAIL → PASS |
| Unchanged | Remaining 13 cases: PASS → PASS, with unchanged structured assertion outcomes |
| Regressed / added / removed cases | None |
| Infrastructure ERROR introduced | None |

For `sales-summer20`, the `structured_assertions` score improved from `0.875` to `1.0`. The only assertion outcome change was the critical, gated `inactive` assertion: FAIL → PASS. The candidate's final promotion was `{"code":"SUMMER20","valid":false,"discount_percent":null,"reason":"inactive"}`; final pricing remained `null`. The other 13 cases retained scores of `1.0`.

This is a like-for-like comparison of the recorded evaluation settings: both runs have dataset hash `c1a73ef207f2cabe3292d743504f7249f4729825d785adff5b6bf14ad6a7b12b`, identical frozen case definitions, 14 cases, and one attempt per case. Scorer configuration, selection, target capabilities, assertion/evidence schema versions, and semantic-evaluation settings match. The recorded model is `gpt-5.6-terra` in both runs. The harness reports `evaluation_config_changed=false`, `dataset_changed=false`, `target_changed=false`, and `model_versions_changed=false`.

The sole configuration-snapshot difference is the observed target prompt version: `phase7-v1` → `phase7-v2`. The harness deliberately excludes target/deployment observations from its evaluator-configuration comparison, so this change does not set `evaluation_config_changed`. Both stored target git revisions are `unknown`; do not infer deployed revisions from local checkout history.

The candidate demonstrates an observed structured regression improvement, not proof of perfect quality or durable repeatability. Semantic evaluation remains `not_measured`, and the full candidate has only one attempt per case. The first V1 deterministic/structured baseline and both stored `RunResult` records remain unchanged for later comparisons.
