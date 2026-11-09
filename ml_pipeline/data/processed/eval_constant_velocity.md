# Trajectory evaluation: constant velocity

## Per horizon

| horizon | n | mean_nm | rmse_nm | median_nm | p90_nm | within_1_nm | within_2_5_nm | within_5_nm | along_mae_nm | cross_mae_nm | altitude_mae_ft | within_500_ft | within_1000_ft |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 min | 38110 | 0.49 | 1.77 | 0.08 | 1.11 | 89.08 | 95.21 | 98.43 | 0.39 | 0.16 | 119.94 | 93.11 | 98.08 |
| 3 min | 32324 | 1.69 | 3.68 | 0.27 | 5.24 | 67.90 | 80.86 | 89.46 | 1.09 | 0.95 | 471.34 | 75.42 | 83.13 |
| 5 min | 27587 | 3.65 | 7.16 | 0.83 | 11.15 | 52.02 | 66.68 | 77.33 | 2.30 | 2.19 | 910.53 | 68.05 | 73.53 |
| 10 min | 18662 | 10.30 | 16.86 | 4.86 | 29.18 | 28.99 | 39.77 | 50.50 | 6.19 | 6.54 | 2231.10 | 50.84 | 62.60 |

## By flight regime

| family | bucket | horizon | n | % within 5 NM | mean NM |
|---|---|---|---|---|---|
| turn | straight | 1 min | 28205 | 98.3 | 0.40 |
| turn | straight | 3 min | 24237 | 93.3 | 1.18 |
| turn | straight | 5 min | 20882 | 82.9 | 2.68 |
| turn | straight | 10 min | 14302 | 54.2 | 8.76 |
| turn | gentle turn | 1 min | 4311 | 98.8 | 0.60 |
| turn | gentle turn | 3 min | 3518 | 84.8 | 2.34 |
| turn | gentle turn | 5 min | 3179 | 71.1 | 4.39 |
| turn | gentle turn | 10 min | 2268 | 50.0 | 10.41 |
| turn | moderate turn | 1 min | 2565 | 98.4 | 0.73 |
| turn | moderate turn | 3 min | 2235 | 80.7 | 2.84 |
| turn | moderate turn | 5 min | 1882 | 61.4 | 6.26 |
| turn | moderate turn | 10 min | 1273 | 37.2 | 14.64 |
| turn | sharp turn | 1 min | 3029 | 98.7 | 0.98 |
| turn | sharp turn | 3 min | 2334 | 65.2 | 4.93 |
| turn | sharp turn | 5 min | 1644 | 36.6 | 11.62 |
| turn | sharp turn | 10 min | 819 | 7.6 | 30.26 |
| vertical | level | 1 min | 26306 | 98.4 | 0.43 |
| vertical | level | 3 min | 22621 | 93.6 | 1.11 |
| vertical | level | 5 min | 19331 | 86.8 | 2.21 |
| vertical | level | 10 min | 13320 | 64.0 | 6.89 |
| vertical | gentle climb/descent | 1 min | 8110 | 98.7 | 0.58 |
| vertical | gentle climb/descent | 3 min | 6538 | 80.1 | 2.89 |
| vertical | gentle climb/descent | 5 min | 5520 | 57.2 | 6.85 |
| vertical | gentle climb/descent | 10 min | 3602 | 22.4 | 18.27 |
| vertical | fast climb/descent | 1 min | 3694 | 98.1 | 0.77 |
| vertical | fast climb/descent | 3 min | 3165 | 79.6 | 3.35 |
| vertical | fast climb/descent | 5 min | 2736 | 51.1 | 7.40 |
| vertical | fast climb/descent | 10 min | 1740 | 5.5 | 19.95 |
| distance to VABB | terminal | 1 min | 8229 | 98.9 | 0.67 |
| distance to VABB | terminal | 3 min | 6485 | 74.4 | 3.63 |
| distance to VABB | terminal | 5 min | 5254 | 45.0 | 8.47 |
| distance to VABB | terminal | 10 min | 2923 | 15.8 | 23.69 |
| distance to VABB | intermediate | 1 min | 4498 | 98.0 | 0.59 |
| distance to VABB | intermediate | 3 min | 3940 | 87.1 | 2.21 |
| distance to VABB | intermediate | 5 min | 3536 | 75.7 | 4.88 |
| distance to VABB | intermediate | 10 min | 2744 | 33.9 | 14.19 |
| distance to VABB | en-route | 1 min | 25383 | 98.4 | 0.42 |
| distance to VABB | en-route | 3 min | 21899 | 94.4 | 1.02 |
| distance to VABB | en-route | 5 min | 18797 | 86.7 | 2.08 |
| distance to VABB | en-route | 10 min | 12995 | 61.8 | 6.47 |
