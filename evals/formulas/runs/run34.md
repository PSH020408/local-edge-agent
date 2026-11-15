# Run 34 — formula set (the report as written by run_formula_set.py)

Vision: qwen3-vl:8b-instruct | Code: d81fe90 + uncommitted changes | 28 formulas | 8.2 min

| Method | Exact | Close | Wrong | Mean seconds |
|---|---|---|---|---|
| page | 17 | 7 | 4 | 5.5 |
| crop2 | 20 | 3 | 5 | 11.9 |

Agreement status against the grade (crop2):

| Status | Exact | Close | Wrong |
|---|---|---|---|
| confirmed | 18 | 1 | 2 |
| close | 0 | 2 | 1 |
| disagree | 2 | 0 | 2 |

| Case | Eq. | Lines | Method | Grade | Similarity | Status | Seconds |
|---|---|---|---|---|---|---|---|
| F01 | (1) | 1 | page | exact | 1.00 | one reading | 12.2 |
| F01 | (1) | 1 | crop2 | close | 0.97 | close | 10.1 |
| F02 | (2) | 1 | page | close | 0.97 | one reading | 1.1 |
| F02 | (2) | 1 | crop2 | exact | 1.00 | confirmed | 9.6 |
| F03 | (3) | 1 | page | exact | 1.00 | one reading | 5.8 |
| F03 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 10.2 |
| F04 | (1) | 1 | page | close | 0.99 | one reading | 6.6 |
| F04 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 12.7 |
| F05 | (3) | 1 | page | wrong | 0.75 | one reading | 0.9 |
| F05 | (3) | 1 | crop2 | exact | 1.00 | disagree | 10.2 |
| F06 | (4) | 1 | page | wrong | 0.86 | one reading | 1.1 |
| F06 | (4) | 1 | crop2 | wrong | 0.86 | confirmed | 10.9 |
| F07 | (1) | 1 | page | exact | 1.00 | one reading | 6.4 |
| F07 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 11.5 |
| F08 | (2) | 1 | page | exact | 1.00 | one reading | 2.8 |
| F08 | (2) | 1 | crop2 | exact | 1.00 | confirmed | 14.0 |
| F09 | (3) | 1 | page | exact | 1.00 | one reading | 6.0 |
| F09 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 10.8 |
| F10 | (4) | 1 | page | exact | 1.00 | one reading | 6.3 |
| F10 | (4) | 1 | crop2 | exact | 1.00 | confirmed | 11.8 |
| F11 | (1) | 1 | page | exact | 1.00 | one reading | 6.9 |
| F11 | (1) | 1 | crop2 | wrong | 0.67 | confirmed | 11.0 |
| F12 | (3) | 1 | page | exact | 1.00 | one reading | 1.4 |
| F12 | (3) | 1 | crop2 | wrong | 0.78 | disagree | 10.2 |
| F13 | (7) | 1 | page | close | 0.98 | one reading | 8.3 |
| F13 | (7) | 1 | crop2 | exact | 1.00 | confirmed | 15.7 |
| F14 | (27) | 1 | page | exact | 1.00 | one reading | 6.6 |
| F14 | (27) | 1 | crop2 | exact | 1.00 | confirmed | 12.2 |
| F15 | (30) | 1 | page | exact | 1.00 | one reading | 6.5 |
| F15 | (30) | 1 | crop2 | close | 0.96 | confirmed | 11.8 |
| F16 | (31) | 2 | page | close | 0.94 | one reading | 10.8 |
| F16 | (31) | 2 | crop2 | wrong | 0.70 | disagree | 17.1 |
| F17 | (46) | 1 | page | exact | 1.00 | one reading | 7.9 |
| F17 | (46) | 1 | crop2 | exact | 1.00 | confirmed | 13.6 |
| F18 | (57) | 1 | page | close | 0.99 | one reading | 8.1 |
| F18 | (57) | 1 | crop2 | close | 0.99 | close | 16.5 |
| F19 | (3) | 2 | page | wrong | 0.84 | one reading | 7.1 |
| F19 | (3) | 2 | crop2 | wrong | 0.87 | close | 12.2 |
| F20 | (11) | 1 | page | close | 0.91 | one reading | 6.5 |
| F20 | (11) | 1 | crop2 | exact | 1.00 | confirmed | 11.6 |
| F21 | (13) | 1 | page | exact | 1.00 | one reading | 1.3 |
| F21 | (13) | 1 | crop2 | exact | 1.00 | confirmed | 10.6 |
| F22 | (22) | 1 | page | exact | 1.00 | one reading | 6.0 |
| F22 | (22) | 1 | crop2 | exact | 1.00 | confirmed | 10.6 |
| F23 | (36) | 1 | page | exact | 1.00 | one reading | 5.7 |
| F23 | (36) | 1 | crop2 | exact | 1.00 | confirmed | 10.0 |
| F24 | (41) | 2 | page | close | 0.94 | one reading | 2.7 |
| F24 | (41) | 2 | crop2 | exact | 1.00 | confirmed | 14.2 |
| F25 | (55) | 2 | page | wrong | 0.81 | one reading | 7.0 |
| F25 | (55) | 2 | crop2 | exact | 1.00 | disagree | 12.9 |
| F26 | (63) | 1 | page | exact | 1.00 | one reading | 6.3 |
| F26 | (63) | 1 | crop2 | exact | 1.00 | confirmed | 11.1 |
| F27 | (1) | 1 | page | exact | 1.00 | one reading | 5.8 |
| F27 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 10.1 |
| F28 | (3) | 1 | page | exact | 1.00 | one reading | 1.0 |
| F28 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 9.9 |

## F01 (1) — page — exact

File: peaf_analog_features.pdf

Expected:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Final:

    P_{\mathrm{tot}} = P_{\mathrm{feat}} + P_{\mathrm{class}} = P_{\mathrm{feat}} + \frac{N_{\mathrm{OPS}} \times FR}{E_{\mathrm{eff}}}

## F01 (1) — crop2 — close

File: peaf_analog_features.pdf

Expected:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Final:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{NOPS \times FR}{E_{eff}}

Reading 1:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{NOPS \times FR}{E_{eff}}

Reading 2:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Differences between the readings: ∅ ↔ _{; ∅ ↔ }

## F02 (2) — page — close

File: peaf_analog_features.pdf

Expected:

    S_{Shannon} = -\sum_{i=0}^{N} p_i \log(p_i)

Final:

    S_{Shannon} = -\sum_{i=1}^{N} p_i \log (p_i)

## F02 (2) — crop2 — exact

File: peaf_analog_features.pdf

Expected:

    S_{Shannon} = -\sum_{i=0}^{N} p_i \log(p_i)

Final:

    S_{Shannon} = -\sum_{i=0}^{N} p_i \log (p_i)

Reading 1:

    S_{Shannon} = -\sum_{i=0}^{N} p_i \log (p_i)

Reading 2:

    S_{Shannon} = -\sum_{i=0}^{N} p_i \log (p_i)

## F03 (3) — page — exact

File: peaf_analog_features.pdf

Expected:

    \text{Encoded feature} = (\text{Flattenedfeature}^T, \text{linspace}(1,N)^T)

Final:

    \text{Encoded feature} = \left( \text{Flattened feature}^T, \text{ linspace}(1,N)^T \right)

## F03 (3) — crop2 — exact

File: peaf_analog_features.pdf

Expected:

    \text{Encoded feature} = (\text{Flattenedfeature}^T, \text{linspace}(1,N)^T)

Final:

    \text{Encoded feature} = (\text{Flattenedfeature}^T, \text{linspace}(1,N)^T)

Reading 1:

    \text{Encoded feature} = (\text{Flattenedfeature}^T, \text{linspace}(1,N)^T)

Reading 2:

    \text{Encoded feature} = (\text{Flattenedfeature}^T, \text{linspace}(1,N)^T)

## F04 (1) — page — close

File: cic_decimation_vlsi.pdf

Expected:

    H(z) = H_I^N(z) . H_C^N(z) = \frac{(1-z^{-RM})^N}{(1-z^{-1})^N} = (\sum_{k=0}^{RM-1} z^{-k})^N

Final:

    H(z)=H_{I}^{N}(z)H_{C}^{N}(z)=\frac{(1-z^{-RM})^{N}}{(1-z^{-1})^{N}}=(\sum_{k=0}^{RM-1}z^{-k})^{N}

## F04 (1) — crop2 — exact

File: cic_decimation_vlsi.pdf

Expected:

    H(z) = H_I^N(z) . H_C^N(z) = \frac{(1-z^{-RM})^N}{(1-z^{-1})^N} = (\sum_{k=0}^{RM-1} z^{-k})^N

Final:

    H(z)=H_{I}^{N}(z).H_{C}^{N}(z)=\frac{(1-z^{-RM})^{N}}{(1-z^{-1})^{N}}=(\sum_{k=0}^{RM-1}z^{-k})^{N}

Reading 1:

    H(z)=H_{I}^{N}(z).H_{C}^{N}(z)=\frac{(1-z^{-RM})^{N}}{(1-z^{-1})^{N}}=(\sum_{k=0}^{RM-1}z^{-k})^{N}

Reading 2:

    H(z)=H_{I}^{N}(z).H_{C}^{N}(z)=\frac{(1-z^{-RM})^{N}}{(1-z^{-1})^{N}}=(\sum_{k=0}^{RM-1}z^{-k})^{N}

## F05 (3) — page — wrong

File: cic_decimation_vlsi.pdf

Expected:

    G_{max} = (RM)^N

Final:

    G_{\max} = \left(RM\right)^{N}

## F05 (3) — crop2 — exact

File: cic_decimation_vlsi.pdf

Expected:

    G_{max} = (RM)^N

Final:

    G_{\mathrm{max}} = (RM)^{N}

Reading 1:

    G_{\mathrm{max}} = (RM)^{N}

Reading 2:

    G_{\max} = (RM)^{N}

Differences between the readings: {max} ↔ \max

## F06 (4) — page — wrong

File: cic_decimation_vlsi.pdf

Expected:

    B_{max} = [N \log_2 R + B_{in} - 1]

Final:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

## F06 (4) — crop2 — wrong

File: cic_decimation_vlsi.pdf

Expected:

    B_{max} = [N \log_2 R + B_{in} - 1]

Final:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

Reading 1:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

Reading 2:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

## F07 (1) — page — exact

File: mri_4d_reconstruction.pdf

Expected:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S}

Final:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S},

## F07 (1) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S}

Final:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S},

Reading 1:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S},

Reading 2:

    y = \mathcal{A}x + n, \quad \mathcal{A} = \mathcal{M}\mathcal{F}\mathcal{S},

## F08 (2) — page — exact

File: mri_4d_reconstruction.pdf

Expected:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \mu_k \|x - z_k\|_2^2

Final:

    z_{k} = x_{k} + \mathcal{R}(x_{k}), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_{2}^{2} + \mu_{k} \left\| x - z_{k} \right\|_{2}^{2}.

## F08 (2) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \mu_k \|x - z_k\|_2^2

Final:

    z_{k} = x_{k} + \mathcal{R}(x_{k}), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_{2}^{2} + \mu_{k} \left\| x - z_{k} \right\|_{2}^{2}.

Reading 1:

    z_{k} = x_{k} + \mathcal{R}(x_{k}), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_{2}^{2} + \mu_{k} \left\| x - z_{k} \right\|_{2}^{2}.

Reading 2:

    z_{k} = x_{k} + \mathcal{R}(x_{k}), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_{2}^{2} + \mu_{k} \left\| x - z_{k} \right\|_{2}^{2}.

## F09 (3) — page — exact

File: mri_4d_reconstruction.pdf

Expected:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r})

Final:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r}),

## F09 (3) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r})

Final:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r}),

Reading 1:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r}),

Reading 2:

    u(\mathbf{r}) = (\alpha - \bar{\alpha}) \varphi(\mathbf{r})

## F10 (4) — page — exact

File: mri_4d_reconstruction.pdf

Expected:

    \hat{x} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \lambda \|x - p\|_2^2

Final:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

## F10 (4) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    \hat{x} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \lambda \|x - p\|_2^2

Final:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

Reading 1:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

Reading 2:

    \hat{x} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_2^2 + \lambda \left\| x - p \right\|_2^2

## F11 (1) — page — exact

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = (h_{pb} * x_{pb})(t) = \int_{-\infty}^{\infty} h_{pb}(u) x_{pb}(t-u) du

Final:

    y_{\mathrm{pb}}(t) = (h_{\mathrm{pb}} * x_{\mathrm{pb}})(t) = \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u) x_{\mathrm{pb}}(t - u) du.

## F11 (1) — crop2 — wrong

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = (h_{pb} * x_{pb})(t) = \int_{-\infty}^{\infty} h_{pb}(u) x_{pb}(t-u) du

Final:

    \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u)x_{\mathrm{pb}}(t-u)du.

Reading 1:

    \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u)x_{\mathrm{pb}}(t-u)du.

Reading 2:

    \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u)x_{\mathrm{pb}}(t-u)du.

## F12 (3) — page — exact

File: ris_tutorial.pdf

Expected:

    X_{pb}(f) = \frac{X(f-f_c) + X^*(-f-f_c)}{\sqrt{2}}

Final:

    X_{\mathrm{pb}}(f) = \frac{X(f - f_c) + X^*(-f - f_c)}{\sqrt{2}}

## F12 (3) — crop2 — wrong

File: ris_tutorial.pdf

Expected:

    X_{pb}(f) = \frac{X(f-f_c) + X^*(-f-f_c)}{\sqrt{2}}

Final:

    \frac{-f_c + X^*(-f - f_c)}{\sqrt{2}}

Reading 1:

    \frac{-f_c + X^*(-f - f_c)}{\sqrt{2}}

Reading 2:

    \frac{-f_c)+X^*(-f-f_c)}{\sqrt{2}}

Differences between the readings: only one reading is usable

## F13 (7) — page — close

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = \sum_{n=1}^{N} (b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb} * x_{pb})(t) = \left(\left[\sum_{n=1}^{N} b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb}\right] * x_{pb}\right)(t)

Final:

    y_{\mathrm{pb}}(t)=\sum_{n=1}^{N}\big(b_{n,\mathrm{pb}}*\partial_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}*x_{\mathrm{pb}}\big)(t)=\left(\left[\sum_{n=1}^{N}b_{n,\mathrm{pb}}*\partial_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}\right]*x_{\mathrm{pb}}\right)(t)

## F13 (7) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = \sum_{n=1}^{N} (b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb} * x_{pb})(t) = \left(\left[\sum_{n=1}^{N} b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb}\right] * x_{pb}\right)(t)

Final:

    y_{\mathrm{pb}}(t)=\sum_{n=1}^{N}\left(b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}*x_{\mathrm{pb}}\right)(t)=\left(\left[\sum_{n=1}^{N}b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}\right]*x_{\mathrm{pb}}\right)(t)

Reading 1:

    y_{\mathrm{pb}}(t)=\sum_{n=1}^{N}\left(b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}*x_{\mathrm{pb}}\right)(t)=\left(\left[\sum_{n=1}^{N}b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}\right]*x_{\mathrm{pb}}\right)(t)

Reading 2:

    y_{\mathrm{pb}}(t)=\sum_{n=1}^{N}\left(b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}*x_{\mathrm{pb}}\right)(t)=\left(\left[\sum_{n=1}^{N}b_{n,\mathrm{pb}}*\vartheta_{n,\mathrm{pb};\theta_{n}}*a_{n,\mathrm{pb}}\right]*x_{\mathrm{pb}}\right)(t)

## F14 (27) — page — exact

File: ris_tutorial.pdf

Expected:

    C = B \log_2(1 + \mathrm{SNR}) = B \log_2\left(1 + \frac{P|h_{\theta}|^2}{BN_0}\right) \text{bit/s}

Final:

    C = B \log_2 \left(1 + \mathrm{SNR}\right) = B \log_2 \left(1 + \frac{P |h_\theta|^2}{B N_0}\right) \quad \mathrm{bit/s}.

## F14 (27) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    C = B \log_2(1 + \mathrm{SNR}) = B \log_2\left(1 + \frac{P|h_{\theta}|^2}{BN_0}\right) \text{bit/s}

Final:

    C = B \log_{2} (1 + \mathrm{SNR}) = B \log_{2} \left(1 + \frac{P |h_{\theta}|^{2}}{B N_{0}}\right) \ \mathrm{bit/s.}

Reading 1:

    C = B \log_{2} (1 + \mathrm{SNR}) = B \log_{2} \left(1 + \frac{P |h_{\theta}|^{2}}{B N_{0}}\right) \ \mathrm{bit/s.}

Reading 2:

    C = B \log_{2} (1 + \mathrm{SNR}) = B \log_{2} \left(1 + \frac{P |h_{\theta}|^{2}}{B N_{0}}\right) \ \mathrm{bit/s.}

## F15 (30) — page — exact

File: ris_tutorial.pdf

Expected:

    \tau_{\theta_n} = \left(\max_{i=1,\dots,N} \tau_{i,a} + \tau_{i,b}\right) - \tau_{n,a} - \tau_{n,b}

Final:

    \tau_{\theta_n} = \left( \max_{i=1,\ldots,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

## F15 (30) — crop2 — close

File: ris_tutorial.pdf

Expected:

    \tau_{\theta_n} = \left(\max_{i=1,\dots,N} \tau_{i,a} + \tau_{i,b}\right) - \tau_{n,a} - \tau_{n,b}

Final:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

Reading 1:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

Reading 2:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

## F16 (31) — page — close

File: ris_tutorial.pdf

Expected:

    \mathrm{SNR} = \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c(\tau_{n,a}+\tau_{n,b}+\tau_{\theta_n})}\right|^2 \le \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c\tau_d}\right|^2 = \frac{P}{BN_0}\left|\sqrt{\rho} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2

Final:

    \mathrm{SNR} = \frac{P}{BN_0} \left| \sqrt{\rho} e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right|^2 \leq \frac{P}{BN_0} \left| \sqrt{\rho} e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right|^2 = \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2.

## F16 (31) — crop2 — wrong

File: ris_tutorial.pdf

Expected:

    \mathrm{SNR} = \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c(\tau_{n,a}+\tau_{n,b}+\tau_{\theta_n})}\right|^2 \le \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c\tau_d}\right|^2 = \frac{P}{BN_0}\left|\sqrt{\rho} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2

Final:

    \leq \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d}+\sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c\tau_d}\right|^2=\frac{P}{BN_0}\left|\sqrt{\rho}+\sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2.

Reading 1:

    \leq \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d}+\sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c\tau_d}\right|^2=\frac{P}{BN_0}\left|\sqrt{\rho}+\sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2.

Reading 2:

    \mathrm{SNR} = \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right| \leq \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c \tau_d} \right|^2 = \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2

Differences between the readings: ∅ ↔ SNR=\frac{P}{BN_0}|\sqrt{\rho}e^{-j2\pif_c\tau_d}+\sum_{n=1}^N\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pif_c(\tau_{n,a}+\tau_{n,b}+\tau_{\theta_n})}|

## F17 (46) — page — exact

File: ris_tutorial.pdf

Expected:

    R \le \frac{B}{K+M-1} \sum_{\nu=0}^{K-1} \log_2\left(1 + \frac{P_\nu}{BN_0}\left(|\boldsymbol{f}_\nu^H \boldsymbol{h}_d| + \|\boldsymbol{f}_\nu^H \boldsymbol{V}^T\|_1\right)^2\right)

Final:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{BN_0} \left( | \boldsymbol{f}_\nu^\mathrm{H} \boldsymbol{h}_d | + \| \boldsymbol{f}_\nu^\mathrm{H} \boldsymbol{V}^\mathrm{T} \|_1 \right)^2 \right)

## F17 (46) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    R \le \frac{B}{K+M-1} \sum_{\nu=0}^{K-1} \log_2\left(1 + \frac{P_\nu}{BN_0}\left(|\boldsymbol{f}_\nu^H \boldsymbol{h}_d| + \|\boldsymbol{f}_\nu^H \boldsymbol{V}^T\|_1\right)^2\right)

Final:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{BN_0} \left( |f_\nu^{\mathrm{H}} h_d| + \| f_\nu^{\mathrm{H}} V^{\mathrm{T}} \|_1 \right)^2 \right)

Reading 1:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{BN_0} \left( |f_\nu^{\mathrm{H}} h_d| + \| f_\nu^{\mathrm{H}} V^{\mathrm{T}} \|_1 \right)^2 \right)

Reading 2:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{B N_0} \left(|f_\nu^H h_d| + \|f_\nu^H V^T\|_1\right)^2 \right)

## F18 (57) — page — close

File: ris_tutorial.pdf

Expected:

    \bar{\boldsymbol{z}}^{(i)}[t] = \sum_{l=1}^{L_d} g^l \boldsymbol{d}(\tau_d^l) \odot \bar{\boldsymbol{x}} + c_t g_{RIS} \boldsymbol{b}^T(\boldsymbol{\phi}_b) \bar{\boldsymbol{\omega}}_{\boldsymbol{\theta}_i} (\boldsymbol{d}(\tau_{RIS}) \odot \bar{\boldsymbol{x}}) + \boldsymbol{w}^{(i)}[t], \quad t = 1, \dots, T/Q

Final:

    \tilde{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\text{RIS}} b^T(\phi_b) \overline{\omega}_{\theta_i} (d(\tau_{\text{RIS}}) \odot \bar{x}) + w^{(i)}[t], \quad t = 1, \ldots, T/Q

## F18 (57) — crop2 — close

File: ris_tutorial.pdf

Expected:

    \bar{\boldsymbol{z}}^{(i)}[t] = \sum_{l=1}^{L_d} g^l \boldsymbol{d}(\tau_d^l) \odot \bar{\boldsymbol{x}} + c_t g_{RIS} \boldsymbol{b}^T(\boldsymbol{\phi}_b) \bar{\boldsymbol{\omega}}_{\boldsymbol{\theta}_i} (\boldsymbol{d}(\tau_{RIS}) \odot \bar{\boldsymbol{x}}) + \boldsymbol{w}^{(i)}[t], \quad t = 1, \dots, T/Q

Final:

    \bar{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\mathrm{RIS}} \mathbf{b}^{\mathrm{T}}(\phi_b) \overline{\mathbf{w}}_{\theta_i} (d(\tau_{\mathrm{RIS}}) \odot \bar{x}) + \mathbf{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Reading 1:

    \bar{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\mathrm{RIS}} \mathbf{b}^{\mathrm{T}}(\phi_b) \overline{\mathbf{w}}_{\theta_i} (d(\tau_{\mathrm{RIS}}) \odot \bar{x}) + \mathbf{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Reading 2:

    \bar{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l \boldsymbol{d}(\tau_d^l) \odot \bar{\boldsymbol{x}} + c_t g_{\mathrm{RIS}} \boldsymbol{b}^{\mathrm{T}}(\phi_b) \overline{\boldsymbol{\omega}}_{\theta_i} \left( \boldsymbol{d}(\tau_{\mathrm{RIS}}) \odot \bar{\boldsymbol{x}} \right) + \boldsymbol{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Differences between the readings: w ↔ \omega

## F19 (3) — page — wrong

File: isac_survey.pdf

Expected:

    \mathcal{P}_e^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr\{\hat{W} \ne i | W = i\}, \quad D = \mathbb{E}\{d(S, \hat{S})\}

Final:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \ne i \mid W = i \right\},

## F19 (3) — crop2 — wrong

File: isac_survey.pdf

Expected:

    \mathcal{P}_e^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr\{\hat{W} \ne i | W = i\}, \quad D = \mathbb{E}\{d(S, \hat{S})\}

Final:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \ne i \,|\, W = i \right\},

Reading 1:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \ne i \,|\, W = i \right\},

Reading 2:

    P_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \ne i \mid W = i \right\},

Differences between the readings: |W ↔ \midW

## F20 (11) — page — close

File: isac_survey.pdf

Expected:

    \mathcal{P}_D \approx Q_1\left(\sqrt{\frac{2P_R|\gamma_d|^2}{\sigma^2}}, \sqrt{2\gamma}\right)

Final:

    \mathcal{P}_{D} \approx Q_{1}\left(\sqrt{\frac{2P_{R}|\gamma d|^{2}}{\sigma^{2}},\sqrt{2\gamma}}\right)

## F20 (11) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathcal{P}_D \approx Q_1\left(\sqrt{\frac{2P_R|\gamma_d|^2}{\sigma^2}}, \sqrt{2\gamma}\right)

Final:

    \mathcal{P}_{D} \approx Q_{1}\left(\sqrt{\frac{2P_{R}|\gamma_{d}|^{2}}{\sigma^{2}}}, \sqrt{2\gamma}\right)

Reading 1:

    \mathcal{P}_{D} \approx Q_{1}\left(\sqrt{\frac{2P_{R}|\gamma_{d}|^{2}}{\sigma^{2}}}, \sqrt{2\gamma}\right)

Reading 2:

    P_{D} \approx Q_{1} \left( \sqrt{ \frac{2 P_{R} |\gamma_{d}|^{2}}{\sigma^{2}} }, \sqrt{2 \gamma} \right)

## F21 (13) — page — exact

File: isac_survey.pdf

Expected:

    \mathbf{Y}_R = \mathbf{G}\mathbf{X} + \mathbf{N}_R

Final:

    \mathbf{Y}_{R} = \mathbf{G}\mathbf{X} + \mathbf{N}_{R}

## F21 (13) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathbf{Y}_R = \mathbf{G}\mathbf{X} + \mathbf{N}_R

Final:

    \mathbf{Y}_{R} = \mathbf{G}\mathbf{X} + \mathbf{N}_{R}

Reading 1:

    \mathbf{Y}_{R} = \mathbf{G}\mathbf{X} + \mathbf{N}_{R}

Reading 2:

    \mathbf{Y}_{R} = \mathbf{G}\mathbf{X} + \mathbf{N}_{R}

## F22 (22) — page — exact

File: isac_survey.pdf

Expected:

    y_R(t) = h_R\sqrt{P_R} s_R(t-\tau) + n_R(t)

Final:

    y_{R}(t)=h_{R}\sqrt{P_{R}}s_{R}(t-\tau)+n_{R}(t)

## F22 (22) — crop2 — exact

File: isac_survey.pdf

Expected:

    y_R(t) = h_R\sqrt{P_R} s_R(t-\tau) + n_R(t)

Final:

    y_{R}(t)=h_{R}\sqrt{P_{R}}s_{R}(t-\tau)+n_{R}(t)

Reading 1:

    y_{R}(t)=h_{R}\sqrt{P_{R}}s_{R}(t-\tau)+n_{R}(t)

Reading 2:

    y_{R}(t)=h_{R}\sqrt{P_{R}}s_{R}(t-\tau)+n_{R}(t)

## F23 (36) — page — exact

File: isac_survey.pdf

Expected:

    \mathbf{X} = \mathbf{W}\mathbf{S}_R

Final:

    \mathbf{X} = \mathbf{W} \mathbf{S}_R

## F23 (36) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathbf{X} = \mathbf{W}\mathbf{S}_R

Final:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R}

Reading 1:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R}

Reading 2:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R},

## F24 (41) — page — close

File: isac_survey.pdf

Expected:

    \hat{B}_q = \begin{cases} 0, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| < \lambda, \\ 1, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| > \lambda, \end{cases}

Final:

    \hat{B}_{q} = \begin{cases} 0, & |{\mathbf{b}}^{H}(\phi_{C}){\mathbf{y}}_{C,q}| < \lambda, \\ 1, & |{\mathbf{b}}^{H}(\phi_{C}){\mathbf{y}}_{C,q}| > \lambda, \end{cases}

## F24 (41) — crop2 — exact

File: isac_survey.pdf

Expected:

    \hat{B}_q = \begin{cases} 0, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| < \lambda, \\ 1, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| > \lambda, \end{cases}

Final:

    \hat{B}_{q} = \begin{cases} 0, & |\mathbf{b}^{H}(\phi_{C})\mathbf{y}_{C,q}| < \lambda, \\ 1, & |\mathbf{b}^{H}(\phi_{C})\mathbf{y}_{C,q}| > \lambda, \end{cases}

Reading 1:

    \hat{B}_{q} = \begin{cases} 0, & |\mathbf{b}^{H}(\phi_{C})\mathbf{y}_{C,q}| < \lambda, \\ 1, & |\mathbf{b}^{H}(\phi_{C})\mathbf{y}_{C,q}| > \lambda, \end{cases}

Reading 2:

    \hat{B}_{q} = \begin{cases} 0, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | < \lambda, \\ 1, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | > \lambda, \end{cases}

## F25 (55) — page — wrong

File: isac_survey.pdf

Expected:

    \min_{\mathbf{X}} \rho\|\mathbf{H}\mathbf{X} - \mathbf{S}_C\|_F^2 + (1-\rho)\|\mathbf{X} - \mathbf{X}_0\|_F^2 \quad \text{s.t.} \quad \|\mathbf{X}\|_F^2 = LP_T

Final:

    \min _{\mathbf{X}} \rho\left\|\mathbf{H X}-\mathbf{S}_{C}\right\|_{F}^{2}+(1-\rho)\left\|\mathbf{X}-\mathbf{X}_{0}\right\|_{F}^{2}

## F25 (55) — crop2 — exact

File: isac_survey.pdf

Expected:

    \min_{\mathbf{X}} \rho\|\mathbf{H}\mathbf{X} - \mathbf{S}_C\|_F^2 + (1-\rho)\|\mathbf{X} - \mathbf{X}_0\|_F^2 \quad \text{s.t.} \quad \|\mathbf{X}\|_F^2 = LP_T

Final:

    \min_{\mathbf{X}} \rho \|\mathbf{H}\mathbf{X} - \mathbf{S}_C\|_F^2 + (1 - \rho) \|\mathbf{X} - \mathbf{X}_0\|_F^2 \quad \text{s.t.} \quad \|\mathbf{X}\|_F^2 = LP_T.

Reading 1:

    \min_{\mathbf{X}} \rho \|\mathbf{H}\mathbf{X} - \mathbf{S}_C\|_F^2 + (1 - \rho) \|\mathbf{X} - \mathbf{X}_0\|_F^2 \quad \text{s.t.} \quad \|\mathbf{X}\|_F^2 = LP_T.

Reading 2:

    \min_{\mathbf{X}} \rho \|\mathbf{H}\mathbf{X} - \mathbf{S}_C\|_F^2 + (1 - \rho) \|\mathbf{X} - \mathbf{X}_0\|_F^2

Differences between the readings: s.t.\|X\|_F^2=LP_T ↔ ∅

## F26 (63) — page — exact

File: isac_survey.pdf

Expected:

    \mathbf{r} = \mathbf{H}_C\mathbf{b} + \mathbf{H}_R\boldsymbol{\alpha} + \mathbf{z}

Final:

    \mathbf{r} = \mathbf{H}_C \mathbf{b} + \mathbf{H}_R \boldsymbol{\alpha} + \mathbf{z}

## F26 (63) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathbf{r} = \mathbf{H}_C\mathbf{b} + \mathbf{H}_R\boldsymbol{\alpha} + \mathbf{z}

Final:

    \mathbf{r} = \mathbf{H}_{C}\mathbf{b} + \mathbf{H}_{R}\boldsymbol{\alpha} + \mathbf{z},

Reading 1:

    \mathbf{r} = \mathbf{H}_{C}\mathbf{b} + \mathbf{H}_{R}\boldsymbol{\alpha} + \mathbf{z},

Reading 2:

    \mathbf{r} = \mathbf{H}_{C}\mathbf{b} + \mathbf{H}_{R}\boldsymbol{\alpha} + \mathbf{z},

## F27 (1) — page — exact

File: expectation_note.pdf

Expected:

    m_n = \frac{1}{n}\sum_{i=1}^{n} x(i)

Final:

    m_{n} = \frac{1}{n} \sum_{i=1}^{n} x(i).

## F27 (1) — crop2 — exact

File: expectation_note.pdf

Expected:

    m_n = \frac{1}{n}\sum_{i=1}^{n} x(i)

Final:

    m_{n} = \frac{1}{n} \sum_{i=1}^{n} x(i).

Reading 1:

    m_{n} = \frac{1}{n} \sum_{i=1}^{n} x(i).

Reading 2:

    m_{n} = \frac{1}{n} \sum_{i=1}^{n} x(i).

## F28 (3) — page — exact

File: expectation_note.pdf

Expected:

    P[A] = \lim_{n\to\infty} \frac{N_A}{n}

Final:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.

## F28 (3) — crop2 — exact

File: expectation_note.pdf

Expected:

    P[A] = \lim_{n\to\infty} \frac{N_A}{n}

Final:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.

Reading 1:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.

Reading 2:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.
