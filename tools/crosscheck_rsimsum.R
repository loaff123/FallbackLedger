# Original complete-data qualification probe. Requires installed rsimsum.
# Run: Rscript --vanilla tools/crosscheck_rsimsum.R /path/to/evidence-directory
# This executes rsimsum itself; it does not emulate package outputs.
args <- commandArgs(trailingOnly = TRUE)
output_dir <- if (length(args)) args[[1]] else '.'
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
if (!requireNamespace('rsimsum', quietly = TRUE)) {
  stop('Install rsimsum from CRAN in your chosen R library before running this probe.')
}
options(digits = 17)
Sys.setenv(TZ = 'UTC')
d <- data.frame(b = c(1, 2, 4, 5), se = rep(1, 4))
d$lo <- d$b - 1.96
d$hi <- d$b + 1.96
s <- rsimsum::simsum(data = d, estvarname = 'b', se = 'se', true = 0,
                    ci.limits = c('lo', 'hi'), dropbig = FALSE,
                    control = list(mcse = TRUE, level = 0.95))
get_stat <- function(name, column) s$summ[s$summ$stat == name, column]
stopifnot(get_stat('bias', 'est') == 3,
          get_stat('mse', 'est') == 11.5,
          get_stat('cover', 'est') == 0.25,
          isTRUE(all.equal(get_stat('bias', 'mcse'), sqrt(10/12))),
          isTRUE(all.equal(get_stat('mse', 'mcse'), sqrt(369/12))),
          isTRUE(all.equal(get_stat('cover', 'mcse'), sqrt(0.25*0.75/4))))
capture.output(sessionInfo(), file = file.path(output_dir, 'session-info.txt'))
capture.output(print(summary(s)), file = file.path(output_dir, 'rsimsum-summary.txt'))
write.csv(d, file.path(output_dir, 'complete-data.csv'), row.names = FALSE)
write.csv(s$summ, file.path(output_dir, 'rsimsum-metrics.csv'), row.names = FALSE)
# Preserve the requested finite metrics with round-trip numeric precision.
selected <- s$summ[s$summ$stat %in% c('bias', 'mse', 'cover'), ]
selected$est <- sprintf('%.17g', selected$est)
selected$mcse <- sprintf('%.17g', selected$mcse)
write.csv(selected, file.path(output_dir, 'rsimsum-requested-metrics.csv'), row.names = FALSE)
cat('R:', R.version.string, '\n')
cat('rsimsum:', as.character(utils::packageVersion('rsimsum')), '\n')
print(selected)
cat('Coverage convention: rsimsum sqrt(p*(1-p)/n); FallbackLedger sample variance uses sqrt(p*(1-p)/(n-1)).\n')
cat('ACTUAL_RSIMSUM_ASSERTIONS_PASSED\n')
