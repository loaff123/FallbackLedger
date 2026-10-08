# Published siman export shape

The source is UCL/siman's simcheck.dta at commit 25b00347f5e9f514ad7708e8bb8d1d798a8e0f54:
https://github.com/UCL/siman/blob/25b00347f5e9f514ad7708e8bb8d1d798a8e0f54/simcheck.dta

This dataset is not bundled. Obtain it under its source terms and install pandas separately to convert Stata data:

```sh
python examples/siman/export.py --input-dta /path/to/simcheck.dta --output-dir siman-input
fallbackledger summarize --study siman-input/study.json --planned siman-input/planned.csv --results siman-input/native_results.csv --mapping siman-input/mapping.json --output-dir siman-report
```

The converter checks SHA-256 07e793f34341e5f5fef57590e405ef62caf5e58e88a6a19acc47374b725a0fb6 and the externally declared three scenarios ×1,000 repetitions ×three methods plan. It rejects a different source rather than inferring a new planned grid from available rows. Lower-level export_records requires an explicit planned_cases argument.

The separate mapping binds dgm/rep/method/b and uses present point estimates for status. It ignores the df column, whose 6,000 absent values do not invalidate point estimates. It does not invent confidence bounds from se/df. MCAR CCA-minus-MI paired bias MCSE is approximately .0083660103; an independent-method calculation would be approximately .0217359070 for these same means and is inappropriate for the paired output.

The independent-case and finite-moment declarations are illustrative assumptions for interpreting these published simulation outputs. This import checks data accounting and paired contributions, not fallback routing or universal properties of the original methods.
