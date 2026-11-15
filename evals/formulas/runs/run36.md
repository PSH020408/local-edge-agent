# Run 36 — formula set (the report as written by run_formula_set.py)

Vision: qwen3-vl:8b-instruct | Code: d81fe90 + uncommitted changes | 28 formulas | 6.0 min

| Method | Exact | Close | Wrong | Mean seconds |
|---|---|---|---|---|
| crop2 | 26 | 2 | 0 | 12.7 |

Agreement status against the grade (crop2):

| Status | Exact | Close | Wrong |
|---|---|---|---|
| confirmed | 23 | 0 | 0 |
| close | 0 | 2 | 0 |
| disagree | 3 | 0 | 0 |

| Case | Eq. | Lines | Method | Grade | Similarity | Status | Seconds |
|---|---|---|---|---|---|---|---|
| F01 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 12.3 |
| F02 | (2) | 1 | crop2 | exact | 1.00 | confirmed | 10.0 |
| F03 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 10.1 |
| F04 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 11.8 |
| F05 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 9.3 |
| F06 | (4) | 1 | crop2 | exact | 1.00 | confirmed | 10.2 |
| F07 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 11.2 |
| F08 | (2) | 1 | crop2 | exact | 1.00 | confirmed | 12.4 |
| F09 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 10.4 |
| F10 | (4) | 1 | crop2 | exact | 1.00 | confirmed | 11.0 |
| F11 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 12.3 |
| F12 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 10.6 |
| F13 | (7) | 1 | crop2 | exact | 1.00 | confirmed | 15.3 |
| F14 | (27) | 1 | crop2 | exact | 1.00 | disagree | 11.1 |
| F15 | (30) | 1 | crop2 | exact | 1.00 | confirmed | 11.2 |
| F16 | (31) | 2 | crop2 | exact | 1.00 | confirmed | 18.6 |
| F17 | (46) | 1 | crop2 | exact | 1.00 | confirmed | 12.8 |
| F18 | (57) | 1 | crop2 | close | 0.99 | close | 14.8 |
| F19 | (3) | 2 | crop2 | exact | 1.00 | disagree | 13.1 |
| F20 | (11) | 1 | crop2 | exact | 1.00 | confirmed | 11.5 |
| F21 | (13) | 1 | crop2 | exact | 1.00 | confirmed | 10.1 |
| F22 | (22) | 1 | crop2 | close | 0.97 | close | 12.1 |
| F23 | (36) | 1 | crop2 | exact | 1.00 | confirmed | 9.6 |
| F24 | (41) | 2 | crop2 | exact | 1.00 | confirmed | 13.2 |
| F25 | (55) | 2 | crop2 | exact | 1.00 | disagree | 41.0 |
| F26 | (63) | 1 | crop2 | exact | 1.00 | confirmed | 11.1 |
| F27 | (1) | 1 | crop2 | exact | 1.00 | confirmed | 9.9 |
| F28 | (3) | 1 | crop2 | exact | 1.00 | confirmed | 9.5 |

## F01 (1) — crop2 — exact

File: peaf_analog_features.pdf

Expected:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Final:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Reading 1:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Reading 2:

    P_{tot} = P_{feat} + P_{class} = P_{feat} + \frac{N_{OPS} \times FR}{E_{eff}}

Check against the image: COMPLETE

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

Check against the image: COMPLETE

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

Check against the image: COMPLETE

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

Check against the image: COMPLETE

## F05 (3) — crop2 — exact

File: cic_decimation_vlsi.pdf

Expected:

    G_{max} = (RM)^N

Final:

    G_{\max} = (RM)^{N}

Reading 1:

    G_{\max} = (RM)^{N}

Reading 2:

    G_{\mathrm{max}} = (RM)^{N}

Check against the image: COMPLETE

## F06 (4) — crop2 — exact

File: cic_decimation_vlsi.pdf

Expected:

    B_{max} = [N \log_2 R + B_{in} - 1]

Final:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

Reading 1:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

Reading 2:

    B_{\max} = \left[ N \log_{2} R + B_{in} - 1 \right]

Check against the image: COMPLETE

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

Check against the image: COMPLETE

## F08 (2) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \mu_k \|x - z_k\|_2^2

Final:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_2^2 + \mu_k \left\| x - z_k \right\|_2^2.

Reading 1:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_2^2 + \mu_k \left\| x - z_k \right\|_2^2.

Reading 2:

    z_k = x_k + \mathcal{R}(x_k), \quad x_{k+1} = \arg\min_{x} \left\| \mathcal{A}x - y \right\|_2^2 + \mu_k \left\| x - z_k \right\|_2^2.

Check against the image: COMPLETE

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

Check against the image: COMPLETE

## F10 (4) — crop2 — exact

File: mri_4d_reconstruction.pdf

Expected:

    \hat{x} = \arg\min_x \|\mathcal{A}x - y\|_2^2 + \lambda \|x - p\|_2^2

Final:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

Reading 1:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

Reading 2:

    \hat{x} = \arg\min_{x} \| \mathcal{A}x - y \|_2^2 + \lambda \| x - p \|_2^2

Check against the image: COMPLETE

## F11 (1) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = (h_{pb} * x_{pb})(t) = \int_{-\infty}^{\infty} h_{pb}(u) x_{pb}(t-u) du

Final:

    y_{\mathrm{pb}}(t) = (h_{\mathrm{pb}} * x_{\mathrm{pb}})(t) = \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u) x_{\mathrm{pb}}(t - u) du.

Reading 1:

    y_{\mathrm{pb}}(t) = (h_{\mathrm{pb}} * x_{\mathrm{pb}})(t) = \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u) x_{\mathrm{pb}}(t - u) du.

Reading 2:

    y_{\mathrm{pb}}(t) = (h_{\mathrm{pb}} * x_{\mathrm{pb}})(t) = \int_{-\infty}^{\infty} h_{\mathrm{pb}}(u) x_{\mathrm{pb}}(t - u) du.

Check against the image: COMPLETE

## F12 (3) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    X_{pb}(f) = \frac{X(f-f_c) + X^*(-f-f_c)}{\sqrt{2}}

Final:

    X_{\mathrm{pb}}(f) = \frac{X(f - f_c) + X^*(-f - f_c)}{\sqrt{2}}

Reading 1:

    X_{\mathrm{pb}}(f) = \frac{X(f - f_c) + X^*(-f - f_c)}{\sqrt{2}}

Reading 2:

    X_{\mathrm{pb}}(f) = \frac{X(f - f_c) + X^*(-f - f_c)}{\sqrt{2}}

Check against the image: COMPLETE

## F13 (7) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    y_{pb}(t) = \sum_{n=1}^{N} (b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb} * x_{pb})(t) = \left(\left[\sum_{n=1}^{N} b_{n,pb} * \vartheta_{n,pb;\theta_n} * a_{n,pb}\right] * x_{pb}\right)(t)

Final:

    y_{\mathrm{pb}}(t) = \sum_{n=1}^{N} (b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} * x_{\mathrm{pb}})(t) = \left( \left[ \sum_{n=1}^{N} b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} \right] * x_{\mathrm{pb}} \right)(t)

Reading 1:

    y_{\mathrm{pb}}(t) = \sum_{n=1}^{N} (b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} * x_{\mathrm{pb}})(t) = \left( \left[ \sum_{n=1}^{N} b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} \right] * x_{\mathrm{pb}} \right)(t)

Reading 2:

    y_{\mathrm{pb}}(t) = \sum_{n=1}^{N} (b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} * x_{\mathrm{pb}})(t) = \left( \left[ \sum_{n=1}^{N} b_{n,\mathrm{pb}} * \vartheta_{n,\mathrm{pb};\theta_n} * a_{n,\mathrm{pb}} \right] * x_{\mathrm{pb}} \right)(t)

Check against the image: COMPLETE

## F14 (27) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    C = B \log_2(1 + \mathrm{SNR}) = B \log_2\left(1 + \frac{P|h_{\theta}|^2}{BN_0}\right) \text{bit/s}

Final:

    C = B \log_2 (1 + \mathrm{SNR}) = B \log_2 \left(1 + \frac{P |h_\theta|^2}{B N_0}\right) \ \mathrm{bit/s}.

Reading 1:

    C = B \log_{2} \left(1 + \frac{P|h_{\theta}|^{2}}{B N_{0}}\right) \text{ bit/s.}

Reading 2:

    C = B \log_2 (1 + \mathrm{SNR}) = B \log_2 \left(1 + \frac{P |h_\theta|^2}{B N_0}\right) \ \mathrm{bit/s}.

Differences between the readings: the second reading has more: ∅ ↔ =Blog_2(1+SNR)

Check against the image: COMPLETE

## F15 (30) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    \tau_{\theta_n} = \left(\max_{i=1,\dots,N} \tau_{i,a} + \tau_{i,b}\right) - \tau_{n,a} - \tau_{n,b}

Final:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

Reading 1:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

Reading 2:

    \tau_{\theta_n} = \left( \max_{i=1,...,N} \tau_{i,a} + \tau_{i,b} \right) - \tau_{n,a} - \tau_{n,b}

Check against the image: COMPLETE

## F16 (31) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    \mathrm{SNR} = \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c(\tau_{n,a}+\tau_{n,b}+\tau_{\theta_n})}\right|^2 \le \frac{P}{BN_0}\left|\sqrt{\rho}e^{-j2\pi f_c\tau_d} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}e^{-j2\pi f_c\tau_d}\right|^2 = \frac{P}{BN_0}\left|\sqrt{\rho} + \sum_{n=1}^{N}\sqrt{\alpha_n\beta_n\gamma}\right|^2

Final:

    \mathrm{SNR} = \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right|^2 \leq \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c \tau_d} \right|^2 = \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2

Reading 1:

    \mathrm{SNR} = \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right|^2 \leq \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c \tau_d} \right|^2 = \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2

Reading 2:

    \mathrm{SNR} = \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c (\tau_{n,a} + \tau_{n,b} + \tau_{\theta_n})} \right|^2 \leq \frac{P}{BN_0} \left| \sqrt{\rho}e^{-j2\pi f_c \tau_d} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} e^{-j2\pi f_c \tau_d} \right|^2 = \frac{P}{BN_0} \left| \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right|^2.

Check against the image: COMPLETE

## F17 (46) — crop2 — exact

File: ris_tutorial.pdf

Expected:

    R \le \frac{B}{K+M-1} \sum_{\nu=0}^{K-1} \log_2\left(1 + \frac{P_\nu}{BN_0}\left(|\boldsymbol{f}_\nu^H \boldsymbol{h}_d| + \|\boldsymbol{f}_\nu^H \boldsymbol{V}^T\|_1\right)^2\right)

Final:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{BN_0} \left(|f_\nu^H h_d| + \|f_\nu^H V^T\|_1\right)^2 \right)

Reading 1:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{BN_0} \left(|f_\nu^H h_d| + \|f_\nu^H V^T\|_1\right)^2 \right)

Reading 2:

    R \le \frac{B}{K + M - 1} \sum_{\nu=0}^{K-1} \log_2 \left(1 + \frac{P_\nu}{B N_0} \left(|f_\nu^H h_d| + \|f_\nu^H V^T\|_1\right)^2 \right)

Check against the image: COMPLETE

## F18 (57) — crop2 — close

File: ris_tutorial.pdf

Expected:

    \bar{\boldsymbol{z}}^{(i)}[t] = \sum_{l=1}^{L_d} g^l \boldsymbol{d}(\tau_d^l) \odot \bar{\boldsymbol{x}} + c_t g_{RIS} \boldsymbol{b}^T(\boldsymbol{\phi}_b) \bar{\boldsymbol{\omega}}_{\boldsymbol{\theta}_i} (\boldsymbol{d}(\tau_{RIS}) \odot \bar{\boldsymbol{x}}) + \boldsymbol{w}^{(i)}[t], \quad t = 1, \dots, T/Q

Final:

    \bar{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\mathrm{RIS}} \mathbf{b}^{\mathrm{T}}(\phi_b) \overline{\mathbf{w}}_{\theta_i} (d(\tau_{\mathrm{RIS}}) \odot \bar{x}) + \mathbf{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Reading 1:

    \bar{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\mathrm{RIS}} \mathbf{b}^{\mathrm{T}}(\phi_b) \overline{\mathbf{w}}_{\theta_i} (d(\tau_{\mathrm{RIS}}) \odot \bar{x}) + \mathbf{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Reading 2:

    \tilde{z}^{(i)}[t] = \sum_{l=1}^{L_d} g^l d(\tau_d^l) \odot \bar{x} + c_t g_{\text{RIS}} \mathbf{b}^T(\phi_b) \overline{\mathbf{w}}_{\theta_i} (d(\tau_{\text{RIS}}) \odot \bar{x}) + \mathbf{w}^{(i)}[t], \quad t = 1, \ldots, T/Q

Differences between the readings: \bar ↔ \tilde

Check against the image: COMPLETE

## F19 (3) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathcal{P}_e^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr\{\hat{W} \ne i | W = i\}, \quad D = \mathbb{E}\{d(S, \hat{S})\}

Final:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \neq i \,|\, W = i \right\}, \quad D = \mathbb{E} \left\{ d \left( S, \hat{S} \right) \right\}

Reading 1:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \ne i \,|\, W = i \right\},

Reading 2:

    \mathcal{P}_{e}^{(n)} = \frac{1}{2^{nR}} \sum_{i=1}^{2^{nR}} \Pr \left\{ \hat{W} \neq i \,|\, W = i \right\}, \quad D = \mathbb{E} \left\{ d \left( S, \hat{S} \right) \right\}

Differences between the readings: the second reading has more: ∅ ↔ ,D=E\{d(S,\hat{S})\}

Check against the image: COMPLETE

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

Check against the image: COMPLETE

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

Check against the image: COMPLETE

## F22 (22) — crop2 — close

File: isac_survey.pdf

Expected:

    y_R(t) = h_R\sqrt{P_R} s_R(t-\tau) + n_R(t)

Final:

    y_{R}(t)=h_{R}\sqrt{P_{R}s_{R}}(t-\tau)+n_{R}(t)

Reading 1:

    y_{R}(t)=h_{R}\sqrt{P_{R}s_{R}}(t-\tau)+n_{R}(t)

Reading 2:

    y_{R}(t)=h_{R}\sqrt{P_{R}}s_{R}(t-\tau)+n_{R}(t)

Differences between the readings: ∅ ↔ }; } ↔ ∅; check against the image: MISSING: The transcription omits the equation number "(22)" which is visible in the image to the right of the equation. Additionally, the transcription incorrectly omits the multiplication symbol betw

Check against the image: MISSING: The transcription omits the equation number "(22)" which is visible in the image to the right of the equation. Additionally, the transcription incorrectly omits the multiplication symbol between the square root term and the argument of the pulse function, which is present in the image as a 

## F23 (36) — crop2 — exact

File: isac_survey.pdf

Expected:

    \mathbf{X} = \mathbf{W}\mathbf{S}_R

Final:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R}

Reading 1:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R}

Reading 2:

    \mathbf{X} = \mathbf{W}\mathbf{S}_{R}

Check against the image: COMPLETE

## F24 (41) — crop2 — exact

File: isac_survey.pdf

Expected:

    \hat{B}_q = \begin{cases} 0, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| < \lambda, \\ 1, & |\mathbf{b}^H(\phi_C)\mathbf{y}_{C,q}| > \lambda, \end{cases}

Final:

    \hat{B}_{q} = \begin{cases} 0, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | < \lambda, \\ 1, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | > \lambda, \end{cases}

Reading 1:

    \hat{B}_{q} = \begin{cases} 0, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | < \lambda, \\ 1, & | \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} | > \lambda, \end{cases}

Reading 2:

    \hat{B}_{q} = \begin{cases} 0, & \left| \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} \right| < \lambda, \\ 1, & \left| \mathbf{b}^{H}(\phi_{C}) \mathbf{y}_{C,q} \right| > \lambda, \end{cases}

Check against the image: COMPLETE

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

Differences between the readings: the first reading has more: s.t.\|X\|_F^2=LP_T ↔ ∅; check against the image: MISSING: The transcription has a superscript 2 on the Frobenius norm in the constraint, but the image shows a subscript F, not a superscript.
The transcription also has a superscript 2 on the Frobeniu

Check against the image: MISSING: The transcription has a superscript 2 on the Frobenius norm in the constraint, but the image shows a subscript F, not a superscript. The transcription also has a superscript 2 on the Frobenius norm in the objective function, but the image shows a subscript F, not a superscript. The transcri

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

Check against the image: COMPLETE

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

Check against the image: COMPLETE

## F28 (3) — crop2 — exact

File: expectation_note.pdf

Expected:

    P[A] = \lim_{n\to\infty} \frac{N_A}{n}

Final:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.

Reading 1:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}.

Reading 2:

    P[A] = \lim_{n \to \infty} \frac{N_A}{n}

Check against the image: COMPLETE
