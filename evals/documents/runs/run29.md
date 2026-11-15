# Run 29 — second holdout: two research papers

Profile: fast | Model: qwen3:8b | Vision: qwen3-vl:8b-instruct | Image planner: qwen3:14b | Documents: qwen3:14b | Code: df47eb8 + uncommitted changes
Cases: 24 | Total: 11.1 min

Grades: ✅ 8, ⚠️ 2, ❌ 11, pass 3

Each answer is printed below as the agent gave it, with the expected answer from the case file and the grade.

| Case | Grade | Reason |
|---|---|---|
| PA1 | ✅ | Correct |
| PA2 | ✅ | Correct |
| PA3 | ⚠️ | Low pass filter named; PCEN left out |
| PA4 | ❌ | Selected p.4 instead of p.2, then a false 'not in the document' |
| PA5 | ❌ | Selected p.4-5, false 'not in the document' |
| PA6 | ❌ | p.2 was selected but cut to its first 3,300 characters; equation (1) is at its end. False 'not in the document' |
| PA7 | ❌ | Selected p.4 instead of p.3; claimed the paper gives no figures for Table 3 |
| PA8 | ❌ | Selected p.4 instead of p.3; 'not described', and expanded WWD as 'Word-World Detection', an invention |
| PA9 | ✅ | Correct |
| PA10 | ✅ | Correct |
| PA11 | ✅ | Whole-document path, 253 s |
| PH1 | pass | Not in the document |
| VA1 | ❌ | Filters and the 16, 2, 2 ratios right, but claims the droop correction filter does not decimate; Figure 1 shows it decimating by 2 |
| VA2 | ✅ | Correct |
| VA3 | ❌ | Selected p.6 instead of p.3, false 'not in the document' |
| VA4 | ❌ | Selected p.4-5 instead of p.3; false 'not in the document' |
| VA5 | ✅ | From the conclusions [p.6] |
| VA6 | ✅ | 220, 163 and 107 MHz with the right pages |
| VA7 | ❌ | Selected p.2 and p.6 instead of p.5; 'no figures given' |
| VA8 | ❌ | Answered from Figure 6 ('all 25 bit'), a different figure |
| VA9 | ❌ | Selected p.3 instead of p.2, 'not mentioned' |
| VA10 | ⚠️ | Two practice questions right; the second states a wrong transfer function from a page whose equation was never read, with no warning |
| VH1 | pass | Not in the document |
| VH2 | pass | Not in the document; its flag is the question's own 'mm²' repeated |

## PA1 — ✅

**File:** peaf_analog_features.pdf  
**Question:** 이 논문에서 말하는 PEAF가 뭐고, 어떤 두 가지 작업으로 평가했어?  
**Expected:** Power-efficient analog acoustic features, validated by fabricated CMOS chips; evaluated on wake word detection (WWD) and keyword spotting (KWS). (pages 1)  
**Grade:** ✅ Correct

**Answer:**

> 이 논문에서 말하는 PEAF는 "Power Efficient Analog Acoustic Features"로, 배터리 수명을 연장하기 위해 설계된 저전력 아날로그 음향 특징을 의미한다 [p.1]. PEAF는 두 가지 작업, 즉 "wake word detection (WWD)"와 "keyword spotting (KWS)"으로 평가되었다 [p.1].
>
> 출처: p.1 (PEAF: Learnable Power Efficient Analog Acoustic Fe)

## PA2 — ✅

**File:** peaf_analog_features.pdf  
**Question:** What are the three basic operations of the analog feature computation, and how do L-PEAF and N-PEAF differ?  
**Expected:** 2nd-order bandpass filtering, an activation function, spike generation with integrate-and-fire (IAF). L-PEAF: absolute value activation; N-PEAF: clipped exponential activation. (pages 2)  
**Grade:** ✅ Correct

**Answer:**

> The three basic operations of the analog feature computation are: 2nd-order bandpass filtering, an activation function, and spike generation based on Integrate-and-Fire (IAF) encoding [p.2].
>
> L-PEAF and N-PEAF differ in the type of activation function they use. L-PEAF uses an absolute value activation function, which gives it a piece-wise linear nature and meets the linearity requirement on circuit implementation [p.2]. In contrast, N-PEAF uses a clipped exponential activation function, which can be implemented with a limiting amplifier and a single voltage-to-current conversion transistor [p.2].
>
> Sources: p.2 (Digital handcrafted (MFCCs) and learnable (LEAFs) )

## PA3 — ⚠️

**File:** peaf_analog_features.pdf  
**Question:** Learn-PEAF는 L-PEAF 구조에 무엇을 추가했어?  
**Expected:** A first-order low pass filter per channel before the IAF, and a PCEN step before the digital classifier; simulated in PyTorch so its parameters can be trained. (pages 2)  
**Grade:** ⚠️ Low pass filter named; PCEN left out

**Answer:**

> Learn-PEAF는 L-PEAF 구조에 추가로 다음과 같은 요소를 포함하고 있다:
>
> 1. 채널당 1차 저역통과 필터 (first-order low pass filter) [p.2].
>
> 출처: p.2 (Digital handcrafted (MFCCs) and learnable (LEAFs) )

## PA4 — ❌

**File:** peaf_analog_features.pdf  
**Question:** 표 1에서 MFCC+ADC, N-PEAF, L-PEAF의 전력은 각각 얼마야?  
**Expected:** MFCC [5] + ADC [6]: 0.34 + 7.2 = 7.5 µW; N-PEAF 0.072 µW; L-PEAF 0.38 µW. (pages 2)  
**Grade:** ❌ Selected p.4 instead of p.2, then a false 'not in the document'

**Answer:**

> 문서는 표 1에서 MFCC+ADC, N-PEAF, L-PEAF의 전력을 명시하지 않았다. 문서는 다른 페이지에서 전력 소비에 대한 정보를 제공하지만, 표 1에 대한 내용은 포함되어 있지 않다.
>
> (문서에 없다는 답입니다. 확인한 페이지: p.4)

## PA5 — ❌

**File:** peaf_analog_features.pdf  
**Question:** What energy efficiency is assumed for the neural network processor, and which frame rates are used for WWD and KWS?  
**Expected:** E_eff = 36.5 · 10^12 OPS/W; FR = 10 fps for WWD and 30 fps for KWS. (pages 2)  
**Grade:** ❌ Selected p.4-5, false 'not in the document'

**Answer:**

> The document does not cover the energy efficiency assumed for the neural network processor or the frame rates used for WWD and KWS.
>
> (The answer says the document does not cover this. Pages checked: p.4, p.5)

## PA6 — ❌

**File:** peaf_analog_features.pdf  
**Question:** Write equation (1) for the total power in LaTeX.  
**Expected:** P_tot = P_feat + P_class = P_feat + (N_OPS × FR) / E_eff. (pages 2)  
**Grade:** ❌ p.2 was selected but cut to its first 3,300 characters; equation (1) is at its end. False 'not in the document'

**Answer:**

> The document does not cover equation (1) for the total power.
>
> (The answer says the document does not cover this. Pages checked: p.4, p.2, p.3)

## PA7 — ❌

**File:** peaf_analog_features.pdf  
**Question:** 표 3에서 L-PEAF baseline, Learn-PEAF, MFCC의 정확도는 각각 얼마야?  
**Expected:** LeNet (B) on KWS: L-PEAF 79.1%, Learn-PEAF 86.4%, MFCC 84.8%. (pages 3)  
**Grade:** ❌ Selected p.4 instead of p.3; claimed the paper gives no figures for Table 3

**Answer:**

> 문서는 표 3에서 L-PEAF baseline, Learn-PEAF, MFCC의 정확도에 대한 구체적인 수치를 제공하지 않습니다. 문서는 "Table 3 shows that all the tested replacements increase the accuracy by a significant amount"라고 언급하지만, 각 모델의 정확도에 대한 구체적인 수치는 제공되지 않았습니다 [p.4].
>
> 출처: p.4 (vs. power consumption. To get an accuracy value th)

## PA8 — ❌

**File:** peaf_analog_features.pdf  
**Question:** WWD 테스트 세트는 어떻게 구성됐어?  
**Expected:** 50 real 'Hey Firefox' recordings, 500 generated positives, 3500 background noise and 3500 negative speech samples, randomly shifted in time. (pages 3)  
**Grade:** ❌ Selected p.4 instead of p.3; 'not described', and expanded WWD as 'Word-World Detection', an invention

**Answer:**

> 문서는 WWD 테스트 세트의 구성을 명확히 설명하지 않았다. 문서는 WWD(Word-World Detection)와 KWS(Keyword Spotting)라는 두 가지 음성 처리 작업에서 아날로그 특징이 디지털 특징보다 우수함을 보여주었지만, WWD 테스트 세트의 구체적인 구성에 대해서는 언급하지 않았다 [p.4].
>
> 출처: p.4 (vs. power consumption. To get an accuracy value th)

## PA9 — ✅

**File:** peaf_analog_features.pdf  
**Question:** For WWD, which analog feature is suggested for the most power-efficient application, and at what cost in accuracy?  
**Expected:** N-PEAF: two times less energy than L-PEAF with a 1% accuracy loss. (pages 4)  
**Grade:** ✅ Correct

**Answer:**

> For the most power-efficient WWD application, N-PEAF is suggested, as it consumes two times less energy compared to L-PEAF [p.4]. This comes at a cost of a 1% accuracy loss compared to L-PEAF [p.4].
>
> Sources: p.4 (vs. power consumption. To get an accuracy value th)

## PA10 — ✅

**File:** peaf_analog_features.pdf  
**Question:** 논문에서 인정한 한계(limitation)는 뭐야?  
**Expected:** Learn-PEAF uses a simplified IAF encoder; L-PEAF and N-PEAF were simulated numerically, not recorded from the real chips. (pages 4)  
**Grade:** ✅ Correct

**Answer:**

> 논문에서 인정한 한계는 다음과 같다:
>
> - Learn-PEAF는 IAF 인코더의 간소화된 버전을 사용한다. 이는 계산 시간을 크게 증가시키고 추출기의 파라미터를 훈련시키는 것을 허용하기 위해서이다 [p.4].
> - L-PEAF와 N-PEAF는 수치적으로 시뮬레이션되었으며, 실제 아날로그 칩의 기록은 취하지 않았다. 이는 [2, 3]에서 수행되었으며, VAD에 대해서만 시뮬레이션이 정확한 것으로 입증되었다 [p.4].
>
> 출처: p.4 (vs. power consumption. To get an accuracy value th)

## PA11 — ✅

**File:** peaf_analog_features.pdf  
**Question:** 이 논문을 다섯 줄로 요약해 줘.  
**Expected:** Analog features (L, N, Learn) for WWD and KWS; power estimates from chips; information-theory analysis finds the IAF bottleneck; Learn-PEAF up to 7% better on KWS than L-PEAF and above MFCC with less power.  
**Grade:** ✅ Whole-document path, 253 s

**Answer:**

> 이 논문은 배터리 수명을 연장하기 위해 웨어러블 및 IoT 스마트 오디오 장치에 사용되는 PEAF(학습 가능한 전력 효율적인 아날로그 음향 특징)를 소개하며, 이는 아날로그 신호 처리(ASP)를 기반으로 전력 효율과 분류 정확도를 동시에 향상시킬 수 있는 새로운 컴퓨팅 패러다임입니다 [p.1]. PEAF의 선형(L-PEAF), 비선형(N-PEAF), 학습 가능한(Learn-PEAF) 변형은 잠금 단어 감지(WWD) 및 키워드 감지(KWS)에서 평가되었으며, 특히 Learn-PEAF는 KWS 정확도를 최대 7% 향상시키며, MFCC보다 적은 전력 소비로 우수한 성능을 보였습니다 [p.1]. 정보 이론 기반의 분석 방법을 통해 특징 추출 과정에서 정보 병목 현상을 식별하고, LEAF에서 영감을 받아 새로운 Learn-PEAF를 설계했습니다 [p.1]. 실험 결과, L-PEAF와 N-PEAF는 전력 소비가 낮은 반면, Learn-PEAF는 작은 분류기에서 5% 이상의 정확도 향상을 보였습니다 [p.4]. 이 연구는 전력 효율이 높고 추론 성능이 우수한 스마트 오디오 장치 개발을 위한 길을 열 수 있다고 결론지었습니다 [p.1].
>
> 출처: p.1 (PEAF: Learnable Power Efficient Analog Acoustic Fe), p.4 (vs. power consumption. To get an accuracy value th)

## PH1 — pass

**File:** peaf_analog_features.pdf  
**Question:** What audio sampling rate and how many microphones did the fabricated chips use in these experiments?  
**Expected:** Neither the sampling rate nor a microphone count is given.  
**Grade:** pass Not in the document

**Answer:**

> The document does not cover the audio sampling rate or the number of microphones used in these experiments.
>
> (The answer says the document does not cover this. Pages checked: p.1, p.4, p.3)

## VA1 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** 이 논문의 데시메이션 시스템은 어떤 필터들로 구성되고, 각 단의 데시메이션 비율은 얼마야?  
**Expected:** Sigma-delta modulator, CIC filter (16), first half band (2), second half band (2), droop correction (2): 6.144 MHz to 48 kHz. (pages 2)  
**Grade:** ❌ Filters and the 16, 2, 2 ratios right, but claims the droop correction filter does not decimate; Figure 1 shows it decimating by 2

**Answer:**

> 이 논문의 데시메이션 시스템은 시그마델타 변조기, CIC 필터, 두 개의 하프밴드 필터, 드롭 커렉션 필터로 구성된다 [p.2]. 
>
> - 시그마델타 변조기 이후에 CIC 필터가 위치하며, 데시메이션 비율은 16:1이다 [p.2].
> - 첫 번째 하프밴드 필터는 데시메이션 비율 2:1을, 두 번째 하프밴드 필터도 데시메이션 비율 2:1을 갖는다 [p.2].
> - 드롭 커렉션 필터는 데시메이션 비율을 변경하지 않으며, 주로 주파수 응답의 패스밴드 감쇠를 보정하는 역할을 한다 [p.2].
>
> 출처: p.2 (0.0002 db. Figure 1 shows 3rd order sigma delta mo)

## VA2 — ✅

**File:** cic_decimation_vlsi.pdf  
**Question:** What sampling frequency and oversampling ratio does the design use, and what is the Nyquist frequency?  
**Expected:** 6.144 MHz, oversampling ratio 128, Nyquist frequency 48 kHz (f_B = 24 kHz). (pages 1)  
**Grade:** ✅ Correct

**Answer:**

> The design uses a sampling frequency of 6.144 MHz [p.1]. The oversampling ratio is 128 [p.1]. The Nyquist frequency is selected to be 48 kHz [p.1].
>
> Sources: p.1 (An Overview of the Decimation process)

## VA3 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** CIC 필터의 N, M, R 값은 각각 얼마로 정했고, 왜 그렇게 정했어?  
**Expected:** N = 5, M = 1, R = 16, to avoid overflow in each stage. (pages 3)  
**Grade:** ❌ Selected p.6 instead of p.3, false 'not in the document'

**Answer:**

> 문서는 CIC 필터의 N, M, R 값에 대한 구체적인 수치나 그 이유를 명시하지 않았습니다. 문서는 CIC 필터의 설계와 성능 향상에 대한 일반적인 내용을 다루고 있지만, N, M, R 값에 대한 정보는 포함되어 있지 않습니다.
>
> (문서에 없다는 답입니다. 확인한 페이지: p.6)

## VA4 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** Write the formulas for the maximum register growth G_max and the output MSB B_max in LaTeX.  
**Expected:** G_max = (RM)^N; B_max = [N log2 R + B_in - 1] (as printed). (pages 3)  
**Grade:** ❌ Selected p.4-5 instead of p.3; false 'not in the document'

**Answer:**

> The document does not cover the formulas for the maximum register growth $ G_{\text{max}} $ and the output MSB $ B_{\text{max}} $.
>
> (The answer says the document does not cover this. Pages checked: p.4, p.5)

## VA5 — ✅

**File:** cic_decimation_vlsi.pdf  
**Question:** 논문에서 CIC 필터의 속도를 높이기 위해 쓴 세 가지 방법은?  
**Expected:** Truncation of LSBs, the modified carry look-ahead adder (MCLA), and the pipeline structure. (pages 3, 4)  
**Grade:** ✅ From the conclusions [p.6]

**Answer:**

> 논문에서 CIC 필터의 속도를 높이기 위해 사용된 세 가지 방법은 다음과 같습니다:
>
> 1. Truncation(절단) [p.6].
> 2. Pipeline 구조 사용 [p.6].
> 3. Modified carry look-ahead adder (MCLA) 사용 [p.6].
>
> 출처: p.6 (FIGURE 8: Signal spectra (a) Output ∑Δ modulator S)

## VA6 — ✅

**File:** cic_decimation_vlsi.pdf  
**Question:** What maximum frequency did the MCLA reach on the FPGA, and how fast is the improved CIC filter compared to the behavioural one?  
**Expected:** MCLA: minimum clock period 4.389 ns, 220 MHz. CIC filter: 163 MHz vs 107 MHz for the behavioural filter. (pages 4, 6)  
**Grade:** ✅ 220, 163 and 107 MHz with the right pages

**Answer:**

> The MCLA reached a maximum frequency of 220 MHz on the FPGA [p.4]. The improved CIC filter has a speed of 163 MHz, which is faster than the behavioural CIC filter that operates at 107 MHz [p.6].
>
> Sources: p.4 (Integrator 1), p.6 (FIGURE 8: Signal spectra (a) Output ∑Δ modulator S)

## VA7 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** SNR은 시그마 델타 모듈레이터 출력과 데시메이션 이후에 각각 몇 dB야?  
**Expected:** 141.56 dB at the modulator output, 145.35 dB after the decimation stages. (pages 5)  
**Grade:** ❌ Selected p.2 and p.6 instead of p.5; 'no figures given'

**Answer:**

> 문서는 시그마 델타 모듈레이터 출력과 데시메이션 이후의 SNR에 대한 구체적인 dB 값을 명시하지 않았다. 다만, 그림 8(a)와 8(b)는 각각 시그마 델타 모듈레이터 출력과 CIC 필터 출력의 SNR을 보여준다고 언급하고 있다. 그러나 구체적인 수치는 제공되지 않았다 [p.6].
>
> 출처: p.6 (FIGURE 8: Signal spectra (a) Output ∑Δ modulator S)

## VA8 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** Figure 4의 truncated CIC 필터에서 Integrator 1부터 5까지 비트 폭은 각각 얼마야?  
**Expected:** Integrators 25, 22, 20, 18 and 16 bits; the five comb stages 16 bits. (pages 4)  
**Grade:** ❌ Answered from Figure 6 ('all 25 bit'), a different figure

**Answer:**

> Figure 6에 따르면, Integrator 1부터 5까지의 비트 폭은 모두 25비트입니다 [p.5].
>
> 출처: p.5 (+ Z)

## VA9 — ❌

**File:** cic_decimation_vlsi.pdf  
**Question:** half band 필터 계수에는 어떤 특징이 있고, 그 덕분에 얻는 장점은?  
**Expected:** All even coefficients are zero except one, which is 0.5; efficient for 2:1 decimation, about 50% less computation than a direct form filter. (pages 2)  
**Grade:** ❌ Selected p.3 instead of p.2, 'not mentioned'

**Answer:**

> 문서는 half band 필터 계수의 특징이나 그로 인해 얻는 장점에 대해 언급하지 않았다. 문서는 CIC 필터와 관련된 내용만 다루고 있다 [p.3].
>
> 출처: p.3 (1 z)

## VA10 — ⚠️

**File:** cic_decimation_vlsi.pdf  
**Question:** 이 논문으로 시험 문제 3개를 만들어 줘. 답과 출처도 같이.  
**Expected:** Three questions whose answers match the paper, each with a correct page citation.  
**Grade:** ⚠️ Two practice questions right; the second states a wrong transfer function from a page whose equation was never read, with no warning

**Answer:**

> ### 문제 1  
> **질문:** 디지털 디시메이션 프로세스는 어떤 통신 시스템에서 주로 사용되며, 이 연구에서는 어떤 변환기의 디시메이션 프로세스를 다루고 있습니까?  
>
> **답:** 디지털 디시메이션 프로세스는 주파수 감소가 필요한 트랜시버에서 사용되며, 이 연구에서는 시그마델타 변환기의 디시메이션 프로세스를 다룹니다.  
> **출처:** [p.1]
>
> ---
>
> ### 문제 2  
> **질문:** CIC 필터의 전달 함수는 어떻게 표현되며, 이 논문에서 CIC 필터의 N, M, R 값은 각각 어떤 값으로 설정되었습니까?  
>
> **답:** CIC 필터의 전달 함수는 $\sum_{k=0}^{RM-1} \frac{z^{-k}}{(1 - z^{-RM})^N}$로 표현되며, 이 논문에서는 N, M, R을 각각 5, 1, 16으로 설정했습니다.  
> **출처:** [p.3]
>
> ---
>
> ### 문제 3  
> **질문:** CIC 필터의 주파수 응답을 개선하기 위해 드롭 커렉션 필터는 어떤 역할을 하며, 전체 시스템의 주파수 응답은 어디에 표시되어 있습니까?  
>
> **답:** 드롭 커렉션 필터는 CIC 필터가 생성한 패스 밴드 감쇠를 보상하여 전체 시스템의 주파수 응답을 평탄하게 만듭니다. 전체 시스템의 주파수 응답은 그림 2에 표시되어 있습니다.  
> **출처:** [p.2]
>
> 출처: p.1 (An Overview of the Decimation process), p.3 (1 z), p.2 (0.0002 db. Figure 1 shows 3rd order sigma delta mo)

## VH1 — pass

**File:** cic_decimation_vlsi.pdf  
**Question:** 논문에서 사용한 FPGA 칩의 정확한 모델명과 소비 전력은?  
**Expected:** Only 'Xilinx FPGA' is named; no model and no power figure.  
**Grade:** pass Not in the document

**Answer:**

> 문서는 FPGA 칩의 정확한 모델명과 소비 전력을 명시하지 않았습니다. [p.4]
>
> 출처: p.4 (Integrator 1)

## VH2 — pass

**File:** cic_decimation_vlsi.pdf  
**Question:** What chip area in mm² does the paper report for the CIC filter?  
**Expected:** No area figure is reported.  
**Grade:** pass Not in the document; its flag is the question's own 'mm²' repeated

**Answer:**

> The document does not cover the chip area in mm² for the CIC filter.
>
> (The answer says the document does not cover this. Pages checked: p.2, p.3, p.1)
