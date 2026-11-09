# Trajectory evaluation: residual LSTM

## Per horizon

| horizon | n | mean_nm | rmse_nm | median_nm | p90_nm | within_1_nm | within_2_5_nm | within_5_nm | along_mae_nm | cross_mae_nm | altitude_mae_ft | within_500_ft | within_1000_ft |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 min | 38110 | 0.45 | 1.73 | 0.07 | 0.97 | 90.28 | 96.07 | 98.46 | 0.37 | 0.13 | 98.63 | 95.11 | 98.93 |
| 3 min | 32324 | 1.38 | 3.10 | 0.23 | 4.18 | 71.71 | 83.71 | 91.96 | 0.83 | 0.81 | 304.26 | 80.71 | 89.71 |
| 5 min | 27587 | 2.69 | 5.37 | 0.67 | 7.78 | 56.11 | 71.52 | 82.90 | 1.45 | 1.80 | 509.58 | 74.16 | 82.63 |
| 10 min | 18662 | 6.41 | 10.47 | 3.23 | 17.15 | 24.73 | 43.97 | 61.31 | 2.81 | 4.96 | 1108.57 | 64.85 | 71.92 |

## By flight regime

| family | bucket | horizon | n | % within 5 NM | mean NM |
|---|---|---|---|---|---|
| turn | straight | 1 min | 28205 | 98.4 | 0.39 |
| turn | straight | 3 min | 24237 | 94.0 | 1.07 |
| turn | straight | 5 min | 20882 | 85.6 | 2.25 |
| turn | straight | 10 min | 14302 | 64.3 | 5.90 |
| turn | gentle turn | 1 min | 4311 | 98.8 | 0.53 |
| turn | gentle turn | 3 min | 3518 | 89.1 | 1.81 |
| turn | gentle turn | 5 min | 3179 | 82.4 | 2.85 |
| turn | gentle turn | 10 min | 2268 | 63.1 | 5.88 |
| turn | moderate turn | 1 min | 2565 | 98.5 | 0.64 |
| turn | moderate turn | 3 min | 2235 | 87.9 | 2.12 |
| turn | moderate turn | 5 min | 1882 | 73.8 | 3.99 |
| turn | moderate turn | 10 min | 1273 | 49.9 | 7.56 |
| turn | sharp turn | 1 min | 3029 | 99.0 | 0.73 |
| turn | sharp turn | 3 min | 2334 | 79.3 | 3.18 |
| turn | sharp turn | 5 min | 1644 | 60.3 | 6.51 |
| turn | sharp turn | 10 min | 819 | 21.2 | 14.99 |
| vertical | level | 1 min | 26306 | 98.4 | 0.40 |
| vertical | level | 3 min | 22621 | 94.2 | 1.00 |
| vertical | level | 5 min | 19331 | 88.4 | 1.93 |
| vertical | level | 10 min | 13320 | 70.0 | 5.06 |
| vertical | gentle climb/descent | 1 min | 8110 | 98.8 | 0.50 |
| vertical | gentle climb/descent | 3 min | 6538 | 87.6 | 2.10 |
| vertical | gentle climb/descent | 5 min | 5520 | 70.9 | 4.19 |
| vertical | gentle climb/descent | 10 min | 3602 | 42.8 | 9.19 |
| vertical | fast climb/descent | 1 min | 3694 | 98.2 | 0.67 |
| vertical | fast climb/descent | 3 min | 3165 | 84.7 | 2.56 |
| vertical | fast climb/descent | 5 min | 2736 | 68.4 | 5.00 |
| vertical | fast climb/descent | 10 min | 1740 | 32.8 | 10.98 |
| distance to VABB | terminal | 1 min | 8229 | 99.0 | 0.56 |
| distance to VABB | terminal | 3 min | 6485 | 84.0 | 2.56 |
| distance to VABB | terminal | 5 min | 5254 | 64.8 | 5.02 |
| distance to VABB | terminal | 10 min | 2923 | 34.8 | 10.81 |
| distance to VABB | intermediate | 1 min | 4498 | 98.1 | 0.52 |
| distance to VABB | intermediate | 3 min | 3940 | 89.2 | 1.80 |
| distance to VABB | intermediate | 5 min | 3536 | 79.5 | 3.49 |
| distance to VABB | intermediate | 10 min | 2744 | 56.6 | 7.68 |
| distance to VABB | en-route | 1 min | 25383 | 98.4 | 0.40 |
| distance to VABB | en-route | 3 min | 21899 | 94.8 | 0.95 |
| distance to VABB | en-route | 5 min | 18797 | 88.6 | 1.88 |
| distance to VABB | en-route | 10 min | 12995 | 68.3 | 5.15 |
