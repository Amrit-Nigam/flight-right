# Trajectory evaluation: tree reference

## Per horizon

| horizon | n | mean_nm | rmse_nm | median_nm | p90_nm | within_1_nm | within_2_5_nm | within_5_nm | along_mae_nm | cross_mae_nm | altitude_mae_ft | within_500_ft | within_1000_ft |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 min | 38110 | 0.43 | 1.70 | 0.07 | 0.91 | 90.75 | 96.23 | 98.46 | 0.36 | 0.12 | 94.84 | 94.99 | 98.86 |
| 3 min | 32324 | 1.27 | 2.96 | 0.20 | 3.91 | 73.35 | 85.03 | 92.63 | 0.80 | 0.70 | 294.72 | 81.10 | 89.89 |
| 5 min | 27587 | 2.39 | 5.02 | 0.50 | 7.07 | 60.06 | 74.73 | 85.08 | 1.35 | 1.51 | 511.70 | 73.55 | 82.72 |
| 10 min | 18662 | 5.57 | 9.51 | 2.33 | 15.28 | 33.07 | 51.43 | 65.66 | 2.60 | 4.11 | 1079.97 | 62.72 | 70.39 |

## By flight regime

| family | bucket | horizon | n | % within 5 NM | mean NM |
|---|---|---|---|---|---|
| turn | straight | 1 min | 28205 | 98.3 | 0.38 |
| turn | straight | 3 min | 24237 | 94.5 | 0.97 |
| turn | straight | 5 min | 20882 | 87.9 | 1.95 |
| turn | straight | 10 min | 14302 | 69.1 | 5.02 |
| turn | gentle turn | 1 min | 4311 | 98.8 | 0.50 |
| turn | gentle turn | 3 min | 3518 | 90.0 | 1.70 |
| turn | gentle turn | 5 min | 3179 | 84.2 | 2.57 |
| turn | gentle turn | 10 min | 2268 | 64.4 | 5.51 |
| turn | moderate turn | 1 min | 2565 | 98.6 | 0.61 |
| turn | moderate turn | 3 min | 2235 | 89.6 | 2.03 |
| turn | moderate turn | 5 min | 1882 | 74.5 | 3.93 |
| turn | moderate turn | 10 min | 1273 | 52.5 | 7.10 |
| turn | sharp turn | 1 min | 3029 | 99.1 | 0.70 |
| turn | sharp turn | 3 min | 2334 | 80.4 | 2.99 |
| turn | sharp turn | 5 min | 1644 | 62.5 | 5.88 |
| turn | sharp turn | 10 min | 819 | 29.4 | 12.98 |
| vertical | level | 1 min | 26306 | 98.4 | 0.39 |
| vertical | level | 3 min | 22621 | 94.6 | 0.93 |
| vertical | level | 5 min | 19331 | 89.7 | 1.72 |
| vertical | level | 10 min | 13320 | 73.6 | 4.33 |
| vertical | gentle climb/descent | 1 min | 8110 | 98.9 | 0.48 |
| vertical | gentle climb/descent | 3 min | 6538 | 89.6 | 1.88 |
| vertical | gentle climb/descent | 5 min | 5520 | 75.2 | 3.65 |
| vertical | gentle climb/descent | 10 min | 3602 | 47.9 | 8.02 |
| vertical | fast climb/descent | 1 min | 3694 | 98.1 | 0.66 |
| vertical | fast climb/descent | 3 min | 3165 | 85.0 | 2.44 |
| vertical | fast climb/descent | 5 min | 2736 | 72.6 | 4.57 |
| vertical | fast climb/descent | 10 min | 1740 | 41.3 | 9.94 |
| distance to VABB | terminal | 1 min | 8229 | 99.0 | 0.54 |
| distance to VABB | terminal | 3 min | 6485 | 85.9 | 2.36 |
| distance to VABB | terminal | 5 min | 5254 | 69.4 | 4.53 |
| distance to VABB | terminal | 10 min | 2923 | 40.5 | 9.76 |
| distance to VABB | intermediate | 1 min | 4498 | 98.1 | 0.50 |
| distance to VABB | intermediate | 3 min | 3940 | 89.0 | 1.74 |
| distance to VABB | intermediate | 5 min | 3536 | 80.8 | 3.30 |
| distance to VABB | intermediate | 10 min | 2744 | 59.9 | 7.08 |
| distance to VABB | en-route | 1 min | 25383 | 98.4 | 0.38 |
| distance to VABB | en-route | 3 min | 21899 | 95.3 | 0.86 |
| distance to VABB | en-route | 5 min | 18797 | 90.3 | 1.62 |
| distance to VABB | en-route | 10 min | 12995 | 72.6 | 4.31 |
